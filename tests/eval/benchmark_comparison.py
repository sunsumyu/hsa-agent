import os
import json
import asyncio
import time
from typing import List, Dict
from loguru import logger
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(override=True)

from app.agents.agent import get_executor, get_prompt
from app.tools import execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge
from tests.eval.metrics import get_hsa_evidence_chain_metric, HSANumericalPrecisionMetric
from deepeval.test_case import LLMTestCase
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from app.infra.model_manager import model_manager

class BenchmarkRunner:
    def __init__(self):
        self.results = []
        self.dataset = self._load_dataset()
        self.evidence_chain_metric = get_hsa_evidence_chain_metric()
        self.precision_metric = HSANumericalPrecisionMetric()

    def _load_dataset(self):
        dataset_path = "tests/eval/golden_dataset.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _create_custom_executor(self, model_id: str, mode: str):
        """动态构建 Agent，支持不同的记忆架构模式。"""
        # 获取 LLM
        llm, resolved_id = model_manager.get_adaptive_llm(model_id=model_id, require_tools=True)
        
        # 定义三种模式的 Prompt 和 Tools
        if mode == "MEMORY_PALACE":
            # 完整模式：层级结构提示词 + 完整工具
            tools = [execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge]
            prompt = get_prompt() # 使用 app.agents.agent 中的复杂全量 Prompt
        elif mode == "STANDARD_RAG":
            # 标准 RAG：扁平化提示词 + 完整工具
            tools = [execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge]
            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一名医疗审计助手。请使用提供的工具检索数据库和专家知识库，回答用户的问题。直接输出结论。"),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
        else: # BASE_LLM
            # 基础模式：简易提示词 + 基础工具（无检索能力）
            tools = [execute_audit_sql, list_tables, calculator]
            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一名医疗审计助手。请基于你的内置知识和提供的基础 SQL 工具回答问题。"),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
            
        # 构建 Agent
        agent = create_openai_tools_agent(llm, tools, prompt)
        return AgentExecutor(agent=agent, tools=tools, verbose=False, return_intermediate_steps=True), resolved_id

    async def run_case(self, model_id: str, mode: str, item: Dict):
        logger.info(f"Running [{model_id}] in [{mode}] mode...")
        
        executor, resolved_id = self._create_custom_executor(model_id, mode)
        
        start_time = time.time()
        try:
            response = await executor.ainvoke({"input": item["input"], "chat_history": []})
            output = str(response["output"])
            latency = time.time() - start_time
            
            # 构建测试用例进行评测
            test_case = LLMTestCase(
                input=item["input"],
                actual_output=output,
                expected_output=item.get("expected_output"),
                context=[item.get("context")]
            )
            
            # 测量指标
            # 提示：GEval (Evidence Chain) 是异步敏感的，有些版本需要 a_measure
            ec_score = await self.evidence_chain_metric.a_measure(test_case)
            np_score = await self.precision_metric.a_measure(test_case)
            
            return {
                "model": model_id,
                "mode": mode,
                "input": item["input"][:30] + "...",
                "evidence_chain": ec_score,
                "numerical_precision": np_score,
                "avg_score": (ec_score + np_score) / 2,
                "latency": latency,
                "status": "Success"
            }
        except Exception as e:
            logger.error(f"Error running case: {e}")
            return {
                "model": model_id,
                "mode": mode,
                "status": f"Error: {str(e)}"
            }

    async def run_benchmark(self, models: List[str]):
        logger.info("Starting Cross-Model RAG Architecture Comparison Matrix...")
        modes = ["STANDARD_RAG", "MEMORY_PALACE"]
        for model in models:
            for mode in modes:
                for item in self.dataset:
                    # 串行运行以避免 API 速率限制 (Rate limit)
                    res = await self.run_case(model, mode, item)
                    self.results.append(res)
                    await asyncio.sleep(2) # 基础频率保护
        
        self.generate_report()

    def generate_report(self):
        report_path = "tests/eval/benchmark_report.md"
        
        # 聚合数据
        summary = {}
        for res in self.results:
            if res["status"] != "Success": continue
            key = (res["model"], res["mode"])
            if key not in summary:
                summary[key] = {"ec": [], "np": [], "latency": []}
            summary[key]["ec"].append(res["evidence_chain"])
            summary[key]["np"].append(res["numerical_precision"])
            summary[key]["latency"].append(res["latency"])

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 记忆宫殿 (Memory Palace) 性能对比报告\n\n")
            f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## 1. 核心模型得分对垒\n\n")
            f.write("| 模型 (Model) | 模式 (Mode) | 证据链得分 (Evidence Chain) | 数值精确度 (NP) | 平均分 | 延迟 (s) |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
            
            # 排序逻辑：模型分组，Palace 优先
            keys = sorted(summary.keys(), key=lambda x: (x[0], x[1] == "MEMORY_PALACE"))
            for model_id, mode in keys:
                data = summary[(model_id, mode)]
                avg_ec = sum(data["ec"]) / len(data["ec"])
                avg_np = sum(data["np"]) / len(data["np"])
                avg_total = (avg_ec + avg_np) / 2
                avg_lat = sum(data["latency"]) / len(data["latency"])
                
                f.write(f"| **{model_id}** | {mode} | {avg_ec:.2f} | {avg_np:.2f} | **{avg_total:.2f}** | {avg_lat:.2f} |\n")
            
            f.write("\n\n## 2. 详细测试结果\n\n")
            f.write("| 输入 (Input) | 模型 | 模式 | 证据链 | 数值 NP | 状态 |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
            for res in self.results:
                if res["status"] == "Success":
                    f.write(f"| {res['input']} | {res['model']} | {res['mode']} | {res['evidence_chain']:.2f} | {res['numerical_precision']:.2f} | ✅ |\n")
                else:
                    f.write(f"| - | {res['model']} | {res['mode']} | - | - | ❌ {res['status']} |\n")

        logger.info(f"Report generated at: {report_path}")

if __name__ == "__main__":
    runner = BenchmarkRunner()
    # 同时对当前三大算力节点进行 Palace 模式下的对垒
    models_to_test = ["gemma-4-31b-it", "qwen-plus", "doubao-pro-32k"]
    asyncio.run(runner.run_benchmark(models_to_test))
