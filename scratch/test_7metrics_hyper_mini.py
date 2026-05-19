# -*- coding: utf-8 -*-
"""
HSA 7-Dimension Metrics Logic Test (Hyper-Minimal)
==================================================
Patches SentenceTransformer and Torch to skip heavy loading.
"""
import os, sys, unittest.mock as mock

# Ensure app is discoverable
sys.path.append(os.getcwd())

# Patch heavy modules before importing model_manager
sys.modules['sentence_transformers'] = mock.MagicMock()
sys.modules['torch'] = mock.MagicMock()

import asyncio, json, time

# Import after patching
from app.infra.model_manager import model_manager

JUDGE_PROMPT = """You are a senior healthcare insurance audit judge.
Score the following audit report on 7 dimensions (0-10 each, total 70):
1. Success       : Was the task completed? Did SQL/code execute?
2. Recall        : Were all suspicious violations found (no omissions)?
3. Precision     : Are flagged violations accurate (no false positives)?
4. Faithfulness  : Is the conclusion grounded in actual data (no hallucination)?
5. Relevance     : Does the report directly answer the original question?
6. Professionalism: Is the audit logic compliant with healthcare insurance regulations?
7. Interpretability: Is the report clear with solid evidence chains?

Return STRICT JSON (no extra text):
{"scores": {"success": 0, "recall": 0, "precision": 0, "faithfulness": 0, "relevance": 0, "professionalism": 0, "interpretability": 0}, "total": 0, "advice": "..."}
"""

MOCK_TASK = "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
MOCK_REPORT = """
# 🔍 医保专项稽核报告

**审计总结**: 本次核查针对 2024 年度“同一天、同一患者、同一医院重复收费”的可疑行为进行了专项扫描。
**审计发现**:
1. 发现患者“张三”在 2024-03-12 于“中心医院”产生了 3 笔完全相同的挂号费。
2. 发现患者“李四”在 2024-05-20 于“中心医院”产生了 2 笔住院诊查费。
**涉及金额**: ¥450.00
**风险等级**: 低
"""

async def run_hyper_mini():
    print("=== HSA 7-Dimension Hyper-Minimal Test ===")
    print("[OK] Heavy models and Torch mocked. Starting Judge...")
    
    # Force use of a specific model for speed if needed
    try:
        judge_llm, judge_model = model_manager.get_adaptive_llm(model_id="doubao-pro-32k")
        print(f"[OK] Judge Model: {judge_model}")

        judge_input = f"{JUDGE_PROMPT}\n\nAudit Task: {MOCK_TASK}\n\nGenerated Report:\n{MOCK_REPORT}"
        
        tj0 = time.time()
        res = await judge_llm.ainvoke(judge_input)
        content = str(res.content)
        
        # Simple JSON extraction
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1:
            eval_res = json.loads(content[s:e+1])
            
            print("\n--- 7-Dimension Scores ---")
            sc = eval_res.get("scores", {})
            for d, v in sc.items():
                print(f"{d:<16}: {v}/10")
            print(f"Total Score: {eval_res.get('total')}/70")
            print(f"Advice: {eval_res.get('advice')}")
        else:
            print(f"Raw Response: {content}")
        print(f"\nCompleted in {time.time()-tj0:.1f}s")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_hyper_mini())
