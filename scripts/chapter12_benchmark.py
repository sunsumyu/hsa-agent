import os
import sys
import asyncio
import json
import time
from datetime import datetime
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
# HF_HOME: use .env or system default

from app.agent_graph import get_graph_executor
from app.model_manager import model_manager

# 1. 工业级裁判 Prompt (符合 Chapter 12 标准)
JUDGE_PROMPT = """
你是一名资深医保稽核专家（裁判员）。请根据【原始任务】和【生成的审计报告】，从以下三个维度打分（各 10 分，总分 30）：
1. **取证忠实度 (Faithfulness)**: 报告中的数据是否严谨地来源于 SQL 结果，有无幻觉？
2. **逻辑专业性 (Professionalism)**: 审计思路是否符合医保稽核规范？
3. **可解释性 (Interpretability)**: 结论是否清晰，是否提供了足够的证据链？

## 评审要求
- expert_advice 必须包含至少一条**具体可操作**的改进建议（指明缺少哪个章节/数据/交叉验证）。
- 即使满分也必须给出"锦上添花"建议，禁止输出空泛赞美。
- expert_advice 使用英文输出。

请以 JSON 格式返回，严禁包含其他文字：
{"scores": {"faithfulness": 9, "professionalism": 8, "interpretability": 9}, "total": 26, "expert_advice": "Specific actionable suggestion..."}
"""

# 2. 精选 5 个 Chapter 12 工业级命题
INDUSTRIAL_CASES = [
    {"id": "QA-01", "prompt": "【基础取证】核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？", "tag": "SQL_PRECISION"},
    {"id": "QA-03", "prompt": "【逻辑路由】对全市结算数据进行性别冲突检查：找出男性患者产生妇科或产科费用的异常明细。", "tag": "BUSINESS_LOGIC"},
    {"id": "QA-04", "prompt": "【多模态穿透】读取处方照片，并与数据库中的 `drug_name` 进行核对，找出名称不符的虚构品项。", "tag": "MULTIMODAL_VISION"},
    {"id": "QA-06", "prompt": "【复杂对撞】跨院审计：查询是否存在同一患者在同一天内，在两家不同等级的医院同时住院（Inpatient Overlap）的情况？", "tag": "COMPLEX_JOIN"},
    {"id": "QA-11", "prompt": "【利益关联】皇亲测试：核查中心医院是否存在与职工共用联系方式（尾号8888）且报销额度异常偏高的患者群？", "tag": "FRAUD_NETWORK"}
]

class Chapter12Evaluator:
    def __init__(self):
        self.executor, _ = get_graph_executor()
        self.results = []
        # 使用 Gemini-1.5-Pro 作为终审裁判，确保公正性
        try:
            self.judge_model, _ = model_manager.get_adaptive_llm(model_id="gemini-1.5-pro")
        except Exception:
            # 降级到 qwen-max
            self.judge_model, _ = model_manager.get_adaptive_llm(model_id="qwen-max")

    async def run_judge(self, prompt: str, report: str) -> dict:
        try:
            full_prompt = f"{JUDGE_PROMPT}\n\n【任务】: {prompt}\n\n【报告】: {report}"
            response = await self.judge_model.ainvoke(full_prompt)
            content = response.content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception as e:
            return {"scores": {"err": 0}, "total": 0, "expert_advice": f"裁判由于 API 压力未给出评分: {str(e)}"}

    async def run(self):
        logger.info("=== 🏁 HSA 审计智能体工业级全面评测 (Chapter 12) ===")
        for case in INDUSTRIAL_CASES:
            logger.info(f"🧪 正在测试 [{case['id']}] - {case['tag']}...")
            start_time = time.time()
            
            # 强制等待，防止 API 级联崩溃
            await asyncio.sleep(45)
            
            try:
                inputs = {"messages": [("user", case['prompt'])]}
                # 开启 50 层深度递归，允许智能体反复修正 SQL
                final_state = await self.executor.ainvoke(inputs, config={"recursion_limit": 50})
                
                duration = time.time() - start_time
                report_content = final_state["messages"][-1].content
                
                # 裁判进场打分
                eval_data = await self.run_judge(case['prompt'], report_content)
                
                self.results.append({
                    "id": case['id'], "tag": case['tag'], 
                    "score": eval_data["total"], "latency": f"{duration:.1f}s",
                    "advice": eval_data["expert_advice"]
                })
                logger.success(f"✅ [{case['id']}] 完成 | 得分: {eval_data['total']}")
            except Exception as e:
                logger.error(f"❌ [{case['id']}] 失败: {e}")
                self.results.append({
                    "id": case['id'], "tag": case['tag'], "score": 0, "latency": "N/A", "advice": f"崩溃报错: {str(e)}"
                })

        self.export_report()

    def export_report(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        report_file = f"data/chapter12_final_report_{ts}.md"
        
        md_content = [
            f"# 🏆 HSA 审计智能体工业级评测报告 (Chapter 12 Standard)",
            f"- **评测时间**: {datetime.now()}",
            f"- **裁判模型**: {getattr(self.judge_model, 'model', 'Adaptive')}\n",
            "| 案例 ID | 技术标签 | 专家评分 (满分 30) | 响应耗时 | 专家建议 |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        
        for res in self.results:
            md_content.append(f"| {res['id']} | {res['tag']} | **{res['score']}** | {res['latency']} | {res['advice']} |")
            
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_content))
        
        logger.success(f"🎊 全面评测报告已生成: {report_file}")

if __name__ == "__main__":
    asyncio.run(Chapter12Evaluator().run())
