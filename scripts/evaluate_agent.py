import os
import sys
import asyncio
import json
from loguru import logger
from typing import Dict, List, Any

# 环境初始化
sys.path.append(os.getcwd())
os.environ["HF_HOME"] = "E:\\hf_cache"

from app.agent_graph import workflow
from app.llm_judge import audit_judge
from app.model_manager import model_manager

class HSAArenaEvaluator:
    """[V53.0] HSA 审计大模型竞技场：Win Rate 胜率对比工具"""
    
    def __init__(self):
        self.cases = [
            {
                "id": "CASE_001_COMPLEX",
                "query": "审计患者 P001 的重复收费情况。注意：该患者在手术期间使用了大量同类耗材。",
                "target": "识别出由于手术复杂性导致的合法合并收费，而非误报。"
            },
            {
                "id": "CASE_002_LOGIC",
                "query": "核查是否存在分解住院行为（同一患者 15 天内因相同诊断再次入院）。",
                "target": "不仅要匹配日期，还要分析诊断代码的语义相似度。"
            }
        ]
        self.stats = {"model_a_wins": 0, "model_b_wins": 0, "ties": 0}

    async def run_single_track(self, model_id: str, query: str) -> str:
        """运行单条审计流水线"""
        # [V53.5] 强制指定模型 ID 用于 Arena 评测
        config = {"configurable": {"thread_id": f"eval_{model_id}", "model_override": model_id}}
        inputs = {"messages": [("user", query)], "session_id": f"eval_{model_id}"}
        
        # 记录执行过程
        logger.info(f"🚀 [ARENA] 模型 {model_id} 正在处理案例...")
        final_state = await workflow.ainvoke(inputs, config=config)
        return final_state["messages"][-1].content

    async def judge_pair(self, query: str, output_a: str, output_b: str) -> str:
        """调用 LLM Judge 进行 Pair-wise 对比判罚"""
        judge_llm = model_manager.get_llm_by_role("planner_heavy")
        
        prompt = f"""
        你是一位资深医保审计专家，现在请你对比两份由 AI 生成的审计报告，并判定哪一份更专业、更准确。
        
        ### 原始需求：
        {query}
        
        ### 报告 A:
        {output_a}
        
        ### 报告 B:
        {output_b}
        
        ### 判罚准则：
        1. 逻辑性：是否识别出了潜在的误报因素？
        2. 证据力：SQL 描述和数值提取是否清晰？
        3. 建议：给出的审计结论是否具备可操作性？
        
        请输出判定结果：[[MODEL_A_WINS]], [[MODEL_B_WINS]], 或 [[TIE]]。并给出简要理由。
        """
        
        response = await judge_llm.ainvoke(prompt)
        content = response.content
        if "[[MODEL_A_WINS]]" in content: return "A"
        if "[[MODEL_B_WINS]]" in content: return "B"
        return "TIE"

    async def evaluate_all(self):
        logger.info("=== 🏆 HSA 审计大模型竞技场 (Arena) 开赛 ===")
        
        for case in self.cases:
            logger.info(f"\n📍 正在评测案例: {case['id']}")
            
            # 运行双轨对比 (模拟 Model A = Qwen, Model B = DeepSeek)
            # 在实际生产中，我们会在这里切换实际的模型配置
            output_a = await self.run_single_track("qwen-plus", case["query"])
            output_b = await self.run_single_track("deepseek-v3", case["query"])
            
            # 判罚
            winner = await self.judge_pair(case["query"], output_a, output_b)
            
            if winner == "A":
                self.stats["model_a_wins"] += 1
                logger.success(f"🚩 判罚结果: Model A (Baseline) 胜出")
            elif winner == "B":
                self.stats["model_b_wins"] += 1
                logger.success(f"🚩 判罚结果: Model B (Challenger) 胜出")
            else:
                self.stats["ties"] += 1
                logger.info(f"🚩 判罚结果: 双方平局")

        # 计算 Win Rate
        total = len(self.cases)
        win_rate = (self.stats["model_b_wins"] / total) * 100
        logger.info("\n=== 📊 最终竞技场战报 ===")
        print(f"Model A Wins: {self.stats['model_a_wins']}")
        print(f"Model B Wins: {self.stats['model_b_wins']}")
        print(f"Ties: {self.stats['ties']}")
        print(f"挑战组 (DeepSeek) 胜率: {win_rate:.2f}%")

if __name__ == "__main__":
    arena = HSAArenaEvaluator()
    asyncio.run(arena.evaluate_all())
