import asyncio
import os
import sys
import json
from loguru import logger

sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.infra.model_manager import model_manager

# 专家评审标准 (七大维度全景评测)
JUDGE_PROMPT = """
你是一名资深医保稽核裁判。请对【审计任务】和【生成的报告】进行严格的定量评审。
评分维度 (每项 10 分，总分 70 分):
1. Success (任务成功率): 任务是否达成，代码/SQL是否成功执行。
2. Recall (召回率): 是否尽可能多地找出了符合条件的违规嫌疑（无遗漏）。
3. Precision (准确率): 找出的违规记录是否精准，没有把正常行为误判为违规。
4. Faithfulness (忠实度): 结论是否完全基于查出的数据，没有任何编造（幻觉）。
5. Relevance (答案相关性): 报告内容是否直接回答了用户最初的问题。
6. Professionalism (专业性): 审计逻辑是否符合医保监管规范与医学常识。
7. Interpretability (可解释性): 报告是否通俗易懂，是否提供了清晰的证据链。

请严格返回 JSON 格式:
{"scores": {"success": 0, "recall": 0, "precision": 0, "faithfulness": 0, "relevance": 0, "professionalism": 0, "interpretability": 0}, "total": 0, "advice": "具体的优化建议..."}
"""

async def test_7_metrics_judge():
    print("[JUDGE] Starting 7-Dimension Expert Judge Test...\n")
    
    # 模拟输入
    mock_task = "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
    mock_report = """
    【审计总结】
    已成功核查 2024 年数据。发现 2 名患者（ID: P001, P045）在同一天内于中心医院被重复收取了挂号费与诊疗费，涉及重复收费 3 笔，总计违规金额 150.00 元。
    
    【证据链】
    1. 患者 P001 在 2024-05-01 产生 2 笔结算单（单号: S1001, S1002）。
    2. 患者 P045 在 2024-06-15 产生 2 笔结算单（单号: S2044, S2045）。
    
    【政策依据】
    根据《医疗保障基金使用监督管理条例》，同一就诊过程不得重复收取门诊诊察费。此行为构成“重复收费”违规。
    """
    
    full_input = f"{JUDGE_PROMPT}\n\n审计任务: {mock_task}\n生成的报告: {mock_report}"
    
    llm, _ = await model_manager.get_llm_by_role("planner_heavy")
    print("[JUDGE] Analyzing and scoring...\n")
    
    try:
        res = await llm.ainvoke(full_input)
        content = str(res.content)
        
        # 提取 JSON 块
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
            
        eval_res = json.loads(json_str.strip())
        
        # 打印格式化报表
        print("=" * 60)
        print("7-DIMENSION EXPERT JUDGE REPORT")
        print("=" * 60)
        s = eval_res.get('scores', {})
        print("   [Metrics Evaluation]")
        print(f"   Success  : {s.get('success',0)}/10")
        print(f"   Recall   : {s.get('recall',0)}/10")
        print(f"   Precision: {s.get('precision',0)}/10")
        print(f"   Faithful : {s.get('faithfulness',0)}/10")
        print(f"   Relevance: {s.get('relevance',0)}/10")
        print(f"   Profess. : {s.get('professionalism',0)}/10")
        print(f"   Interpret: {s.get('interpretability',0)}/10")
        print("-" * 60)
        print(f"   Total Score: {eval_res.get('total', 0)} / 70")
        print(f"   Advice:\n   {eval_res.get('advice', '无')}")
        print("=" * 60)
        
    except Exception as e:
        print(f"Parsing Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_7_metrics_judge())
