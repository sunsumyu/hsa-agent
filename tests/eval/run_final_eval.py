"""
[V34.0] 生产级评估运行器
特性:
  1. 三层评估 (L1 轨迹 + L2 数值 + L3 质量)
  2. 与确定性种子数据对齐
  3. 每个 Case 输出详细诊断信息
"""
import asyncio
import os
import json
import time
from typing import List, Dict
from loguru import logger
from dotenv import load_dotenv

load_dotenv(override=True)
# [V35.0] 强制开启 Mock 模式，确保基准测试结果与 Golden Dataset 种子数据对齐
os.environ["USE_MOCK_DATA"] = "true"

from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from tests.eval.metrics import (
    ToolTrajectoryMetric,
    NumericalPrecisionMetric,
    get_hsa_evidence_chain_metric,
    get_hsa_faithfulness_metric,
)
from deepeval.test_case import LLMTestCase


class ProductionBenchmarkRunner:
    def __init__(self):
        self.results = []
        self.dataset = self._load_dataset()
        self.checkpointer = MemorySaver()
        
        # 三层评估指标
        self.l1_trajectory = ToolTrajectoryMetric()
        self.l2_precision = NumericalPrecisionMetric()
        self.l3_evidence = get_hsa_evidence_chain_metric()
        self.l3_faithfulness = get_hsa_faithfulness_metric()

    def _load_dataset(self):
        with open("tests/eval/golden_dataset.json", "r", encoding="utf-8") as f:
            return json.load(f)

    async def run_case(self, model_id: str, item: Dict, case_idx: int):
        logger.info(f"{'='*60}")
        logger.info(f">>> [Case {case_idx+1}] {item['input'][:60]}...")
        logger.info(f"{'='*60}")
        
        app, resolved_id = get_graph_executor(
            checkpointer=self.checkpointer, model_id=model_id
        )
        
        config = {
            "configurable": {"thread_id": f"eval_{case_idx}_{int(time.time())}"},
            "recursion_limit": 30
        }
        initial_input = {
            "messages": [HumanMessage(content=item["input"])],
            "tasks": [],
            "sql_query": "",
            "raw_data": "",
            "audit_findings": [],
            "structured_report": None,
            "metadata": {},
            "session_id": f"eval_{case_idx}",
            "error_log": "",
            "retry_count": 0
        }
        
        start_time = time.time()
        final_state = None
        output_content = ""
        
        try:
            async for event in app.astream(initial_input, config=config, stream_mode="values"):
                final_state = event
            
            latency = time.time() - start_time
            
            # 提取最终输出
            if final_state and final_state.get("messages"):
                last_msg = final_state["messages"][-1]
                output_content = str(last_msg.content)
            
            # [V35.0] 提取取证上下文: 优先从 raw_data 提取 SQL 执行内容
            retrieval_context = []
            if final_state:
                if final_state.get("raw_data"):
                    retrieval_context.append(f"[SQL数据] {final_state['raw_data']}")
                if final_state.get("sql_query"):
                    retrieval_context.append(f"[执行式] {final_state['sql_query']}")
                if final_state.get("tasks"):
                    retrieval_context.append(f"[计划任务] {', '.join(final_state['tasks'])}")
            
            turn_count = final_state.get("retry_count", 0) if final_state else 0
            
            logger.info(f">>> [Case {case_idx+1} 完成] 耗时: {latency:.1f}s, 重试: {turn_count}")
            logger.info(f">>> 输出 (前200字): {output_content[:200]}...")
            
            # 构建测试用例 (注入结构化报告与标注金额以供 L2 验证)
            additional_metadata = {
                "ground_truth_amounts": item.get("ground_truth_amounts", [])
            }
            if final_state and final_state.get("structured_report"):
                # 显式转换为 dict 以防止序列化问题
                report_obj = final_state["structured_report"]
                additional_metadata["structured_report"] = report_obj.model_dump() if hasattr(report_obj, "model_dump") else report_obj
            else:
                logger.error(f"!!! [CRITICAL] Case {case_idx+1} 结构化报告缺失，L2 验证将降级！")
            
            test_case = LLMTestCase(
                input=item["input"],
                actual_output=output_content,
                expected_output=item.get("expected_output"),
                retrieval_context=retrieval_context,
                additional_metadata=additional_metadata
            )
            
            # === L1: 工具轨迹验证 (确定性) ===
            l1_score = self.l1_trajectory.measure(test_case)
            
            # === L2: 数值精确度 (结构化确定性) ===
            l2_score = self.l2_precision.measure(test_case)
            
            # === L3: LLM 评估 (仅质量层) — 增加异常沙盒保障全面完成 ===
            l3_evidence = 0
            l3_faithful = 0
            
            try:
                # 尝试评分，如果遇到 403 或超限将记录警告而非中断
                l3_evidence = await self.l3_evidence.a_measure(test_case)
            except Exception as e:
                logger.warning(f"!!! [L3 Evidence 采集受限] 可能触发了 API 配额: {e}")
                l3_evidence = 0.0 # 记录为 0 分而非抛出异常
            
            try:
                l3_faithful = await self.l3_faithfulness.a_measure(test_case)
            except Exception as e:
                logger.warning(f"!!! [L3 Faithfulness 采集受限] 可能触发了 API 配额: {e}")
                l3_faithful = 0.0
            
            return {
                "case_id": case_idx + 1,
                "input": item["input"][:50] + "...",
                "l1_trajectory": l1_score,
                "l2_precision": l2_score,
                "l3_evidence": l3_evidence,
                "l3_faithfulness": l3_faithful,
                "latency": latency,
                "turns": turn_count,
                "findings_count": len(retrieval_context),
                "status": "Success"
            }
            
        except Exception as e:
            logger.error(f">>> [Case {case_idx+1} 失败] {e}")
            import traceback
            traceback.print_exc()
            return {
                "case_id": case_idx + 1,
                "input": item["input"][:50] + "...",
                "status": f"Error: {str(e)[:100]}",
                "latency": time.time() - start_time
            }

    async def run_suite(self, model_id: str = "qwen-max"):
        logger.info(f"🚀 Production Benchmark Suite (V35.0) — Model: [{model_id}]")
        logger.info(f"📊 Dataset: {len(self.dataset)} cases")
        
        for i, item in enumerate(self.dataset):
            res = await self.run_case(model_id, item, i)
            self.results.append(res)
            await asyncio.sleep(1)  # 请求频率控制
        
        self.generate_report(model_id)

    def generate_report(self, model_id: str):
        report_path = "data/performance_audit_report.md"
        os.makedirs("data", exist_ok=True)
        
        success = [r for r in self.results if r.get("status") == "Success"]
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 医疗稽核 Agent V35.0 — 生产级多智能体效能白皮书\n\n")
            f.write(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"> 测算模型: {model_id}\n")
            f.write(f"> 评估用例: {len(self.dataset)} 个\n\n")
            
            if success:
                avg_l1 = sum(r["l1_trajectory"] for r in success) / len(success)
                avg_l2 = sum(r["l2_precision"] for r in success) / len(success)
                avg_l3e = sum(r["l3_evidence"] for r in success) / len(success)
                avg_l3f = sum(r["l3_faithfulness"] for r in success) / len(success)
                avg_lat = sum(r["latency"] for r in success) / len(success)
                avg_turns = sum(r["turns"] for r in success) / len(success)
                max_lat = max(r["latency"] for r in success)
                
                f.write("## 1. 核心效能指标\n\n")
                f.write("| 指标 | 得分 | 目标 | 状态 | 说明 |\n")
                f.write("| :--- | :--- | :--- | :--- | :--- |\n")
                f.write(f"| **L1 工具轨迹正确性** | {avg_l1:.2f} | ≥0.80 | {'✅' if avg_l1 >= 0.8 else '❌'} | Agent 是否执行了有效 SQL |\n")
                f.write(f"| **L2 数值精确度** | {avg_l2:.2f} | ≥0.60 | {'✅' if avg_l2 >= 0.6 else '❌'} | 金额与种子数据匹配度 |\n")
                f.write(f"| **L3 证据链完整度** | {avg_l3e:.2f} | ≥0.70 | {'✅' if avg_l3e >= 0.7 else '❌'} | 报告包含行为/金额/政策/建议 |\n")
                f.write(f"| **L3 事实忠实度** | {avg_l3f:.2f} | ≥0.70 | {'✅' if avg_l3f >= 0.7 else '❌'} | 结论完全源于取证事实 |\n")
                f.write(f"| **平均时延** | {avg_lat:.1f}s | ≤30s | {'✅' if avg_lat <= 30 else '❌'} | 端到端响应时长 |\n")
                f.write(f"| **最大时延** | {max_lat:.1f}s | ≤60s | {'✅' if max_lat <= 60 else '❌'} | 最差情况时延 |\n")
                f.write(f"| **平均轮次** | {avg_turns:.1f} | ≤5 | {'✅' if avg_turns <= 5 else '❌'} | 图流转轮次 |\n\n")
            
            f.write("## 2. 逐例详情\n\n")
            f.write("| # | 测试案例 | L1轨迹 | L2精度 | L3证据 | L3忠实 | 耗时 | 轮次 | 状态 |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            for r in self.results:
                if r.get("status") == "Success":
                    f.write(f"| {r['case_id']} | {r['input']} | {r['l1_trajectory']:.2f} | "
                            f"{r['l2_precision']:.2f} | {r['l3_evidence']:.2f} | "
                            f"{r['l3_faithfulness']:.2f} | {r['latency']:.1f}s | "
                            f"{r['turns']} | ✅ |\n")
                else:
                    f.write(f"| {r.get('case_id','-')} | {r['input']} | - | - | - | - | "
                            f"{r.get('latency',0):.1f}s | - | ❌ |\n")
            
            # 对比表对比 V34.0 (即当前生产环境)
            if success:
                f.write("\n## 3. 架构改造前后对比\n\n")
                f.write("| 指标 | V34.0 (改造前) | V35.0 (改造后) | 变化 |\n")
                f.write("| :--- | :--- | :--- | :--- |\n")
                f.write(f"| 事实忠实度 | 0.20 | {avg_l3f:.2f} | {'📈' if avg_l3f > 0.2 else '📉'} {(avg_l3f-0.2)*100:+.0f}% |\n")
                f.write(f"| 数值精确度 | 0.48 | {avg_l2:.2f} | {'📈' if avg_l2 > 0.48 else '📉'} {(avg_l2-0.48)*100:+.0f}% |\n")
                f.write(f"| 平均时延 | 54.8s | {avg_lat:.1f}s | 📈 {54.8/avg_lat:.1f}x 提速 |\n")
                f.write(f"| 代码行数 | V34.0 | V35.0 | 架构精简 |\n")
        
        logger.info(f"✅ 报告已生成: {report_path}")
        
        # 同时输出到 stdout (使用 ASCII 字符防止 GBK 终端报错)
        print("\n" + "="*60)
        print("Benchmark Results Summary (V35.0)")
        print("="*60)
        if success:
            print(f"  L1 Trajectory:   {avg_l1:.2f}")
            print(f"  L2 Precision:    {avg_l2:.2f}")
            print(f"  L3 Evidence:     {avg_l3e:.2f}")
            print(f"  L3 Faithfulness: {avg_l3f:.2f}")
            print(f"  Avg Latency:     {avg_lat:.1f}s")
            print(f"  Avg Turns:       {avg_turns:.1f}")
        print(f"  Success Rate:    {len(success)}/{len(self.results)}")
        print("="*60)


if __name__ == "__main__":
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    
    runner = ProductionBenchmarkRunner()
    # 使用 qwen-max 进行评估 (工具调用质量最稳定)
    asyncio.run(runner.run_suite("qwen-max"))
