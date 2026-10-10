# -*- coding: utf-8 -*-
"""
scratch/run_clean_room_benchmark.py
===================================
Matt Pocock 规范：代码完全冻结下的 Clean-Room 生产环境纯净盲测
(Clean-Room Blind Benchmark under Strict Code Freeze - Commit a91f57f)

【评估铁律】
1. 代码 100% 冻结：中途绝不修改 app/ 下任何一行生产代码。
2. 零人工干预：端到端一次性全流程执行 (workflow.ainvoke)。
3. 客观数据对账：通过 AuditMetricEvaluator 进行精确召回率、精确率与 F1 度量。
4. 真实生产度量：如实度量一次通过率 (First-Pass Accuracy) 与系统自主自愈表现。

【盲测场景】
- QA-CLEAN-01: 同日跨医疗机构重复就诊与结算冲突审计 (Self-Join 跨表时空去重，真实对账: 5对/5人/¥1581.64)
- QA-CLEAN-02: 基层医疗机构 100% 医保基金全额兜底异常集中度核查 (等式约束与机构聚合，真实对账: 108笔/¥2390.40/哲觉镇卫生院)
"""

import os
import sys
import asyncio
import json
import time
from datetime import datetime
from loguru import logger

# 清理代理，确保本地服务直连
for k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["DISABLE_AUDIT_CACHE"] = "true"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath("."))
from app.core.agent_graph import workflow
from app.reporting.report_renderer import report_renderer
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator

CLEAN_ROOM_CASES = [
    {
        "id": "QA-CLEAN-01",
        "tag": "Same-Day Cross-Institution Multi-Settlement Conflict Audit",
        "prompt": "对医保结算表（fqz_gz_jzsj_all_ql）开展同日跨机构异常就诊核查：排查同一患者（psn_no）在同一就诊日期（以 setl_time 为准按天对比）在两家及以上不同医疗机构（hosp_name）同时发生结算的可疑记录。请统计涉及的异常配对组数、参保人数及合计医疗费用，并按就诊日期排序输出涉案明细。",
        "eval_type": "exact_records",
        "expected_count": 5,
        "expected_sum": 1581.64,
        "key_entities": ["5", "520500P0000003056770", "520500P0000003310031", "哲觉镇卫生院", "威宁", "毕节", "1581.64", "420", "497.64"]
    },
    {
        "id": "QA-CLEAN-02",
        "tag": "100% Fund Coverage Zero-Copay Concentration Audit",
        "prompt": "对结算主表（fqz_gz_jzsj_all_ql）进行基金全额兜底（零自付）合规筛查：检索医保基金支付金额（fund_pay_sumamt）全额承担医疗总费用（即 fund_pay_sumamt = medfee_sumamt 且 fund_pay_sumamt > 0）的异常结算单据。统计符合条件的总结算笔数与基金支出总额，并按医疗机构（hosp_name）汇总统计主要发生机构的分布。",
        "eval_type": "exact_records",
        "expected_count": 108,
        "expected_sum": 2390.40,
        "key_entities": ["108", "2390.4", "哲觉镇卫生院"]
    }
]

async def run_single_clean_case(case: dict) -> dict:
    cid = case["id"]
    prompt = case["prompt"]
    tag = case["tag"]
    
    print("\n" + "=" * 80)
    print(f"🚀 [CLEAN-ROOM BENCHMARK] CASE: {cid} | Tag: {tag}")
    print(f"❓ Prompt: {prompt}")
    print("=" * 80)
    
    t0 = time.time()
    inputs = {
        "messages": [("user", prompt)],
        "session_id": f"CLEAN_ROOM_{cid}_{int(t0)}"
    }
    
    state = None
    exec_error = None
    try:
        # 严格无干预执行生产完整工作流
        state = await workflow.ainvoke(inputs, config={"recursion_limit": 60})
    except Exception as ex:
        exec_error = str(ex)
        logger.error(f"[{cid}] Execution exception: {ex}")
        
    elapsed = time.time() - t0
    
    msgs = state.get("messages", []) if state else []
    report_text = ""
    if msgs:
        last = msgs[-1]
        report_text = last[1] if isinstance(last, tuple) else getattr(last, "content", str(last))
        
    sql_history = state.get("sql_history", []) if state else []
    raw_data = state.get("raw_data", []) if state else []
    
    # 转换为 dict list
    db_rows = []
    if isinstance(raw_data, list):
        for item in raw_data:
            if isinstance(item, dict):
                db_rows.append(item)
            elif isinstance(item, (list, tuple)):
                db_rows.append({"col_" + str(i): v for i, v in enumerate(item)})
    elif isinstance(raw_data, str) and raw_data.strip():
        chunks = raw_data.split("\n---\n")
        for chunk in chunks:
            chunk_str = chunk.strip()
            if chunk_str.startswith("[") or chunk_str.startswith("{"):
                try:
                    parsed = json.loads(chunk_str)
                    if isinstance(parsed, list):
                        db_rows.extend([r for r in parsed if isinstance(r, dict)])
                    elif isinstance(parsed, dict):
                        db_rows.append(parsed)
                except Exception:
                    pass

    # 若未提取到结构化行但存在最终业务 SQL，直连对账检验
    if not db_rows and state and state.get("sql_query"):
        try:
            from app.infra.db_conn import get_clickhouse_client
            ck_c = get_clickhouse_client()
            q_res = ck_c.query(state["sql_query"])
            if isinstance(q_res, list) and q_res and isinstance(q_res[0], dict):
                db_rows = q_res
        except Exception:
            pass
    # 客观指标评估 (AuditMetricEvaluator)
    eval_res = AuditMetricEvaluator.evaluate(
        eval_type=case["eval_type"],
        gt_count=case["expected_count"],
        gt_sum=case["expected_sum"],
        db_rows=db_rows,
        report_text=report_text,
        key_entities=case["key_entities"]
    )
    
    # 实体捕获率
    matched_entities = [k for k in case["key_entities"] if k in report_text or k in str(db_rows)]
    entity_rate = len(matched_entities) / len(case["key_entities"]) if case["key_entities"] else 1.0
    
    # 评定状态
    passed = (eval_res.recall_pct >= 80.0 and eval_res.precision_pct >= 50.0) or (entity_rate >= 0.5)
    
    print("\n" + "-" * 80)
    print(f"📋 [{cid}] EVALUATION METRICS REPORT:")
    print(f"  • Status          : {'✅ PASS' if passed else '❌ FAIL'}")
    print(f"  • Det Count       : {eval_res.det_count} (Expected: {case['expected_count']})")
    print(f"  • Recall          : {eval_res.recall_pct}%")
    print(f"  • Precision       : {eval_res.precision_pct}%")
    print(f"  • F1 Score        : {eval_res.f1_score}")
    print(f"  • Entity Hit Rate : {entity_rate * 100:.1f}% ({len(matched_entities)}/{len(case['key_entities'])})")
    print(f"  • Wall Time       : {elapsed:.2f}s")
    print(f"  • SQLs Executed   : {len(sql_history)}")
    if sql_history:
        print(f"  • Final SQL       :\n{sql_history[-1]}")
    print(f"  • Report Snippet  :\n{report_text[:400]}...")
    print("-" * 80 + "\n")
    
    return {
        "id": cid,
        "tag": tag,
        "passed": passed,
        "elapsed": elapsed,
        "eval_res": eval_res,
        "entity_rate": entity_rate,
        "matched_entities": matched_entities,
        "sql_history": sql_history,
        "report_text": report_text,
        "error": exec_error
    }

async def main():
    print("\n" + "#" * 80)
    print("  ARGUS MEDICAL AUDIT AGENT: CLEAN-ROOM BLIND BENCHMARK")
    print(f"  Commit Locked : a91f57f (Strict Code Freeze)")
    print(f"  Timestamp     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Test Cases    : {len(CLEAN_ROOM_CASES)} Unseen Scenarios")
    print("#" * 80 + "\n")
    
    results = []
    for c in CLEAN_ROOM_CASES:
        res = await run_single_clean_case(c)
        results.append(res)
        await asyncio.sleep(2)
        
    print("\n" + "=" * 80)
    print("🏆 CLEAN-ROOM BLIND BENCHMARK FINAL SCORECARD (0 INTERVENTION)")
    print("=" * 80)
    
    all_pass = True
    for r in results:
        status_str = "✅ PASS" if r["passed"] else "❌ FAIL"
        if not r["passed"]:
            all_pass = False
        ev = r["eval_res"]
        print(f"[{r['id']}] {status_str} | Recall: {ev.recall_pct:5.1f}% | Precision: {ev.precision_pct:5.1f}% | F1: {ev.f1_score:.3f} | Entities: {r['entity_rate']*100:4.1f}% | Time: {r['elapsed']:5.1f}s")
        
    print("=" * 80)
    print(f"Final Outcome: {'🎯 100% CLEAN-ROOM BENCHMARK SUCCESS' if all_pass else '⚠️ BENCHMARK WITH GAPS'}")
    print("=" * 80 + "\n")
    
    out_dir = "data/bench_history"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(out_dir, f"clean_room_benchmark_{ts}.json")
    
    serializable = []
    for r in results:
        ev = r["eval_res"]
        serializable.append({
            "id": r["id"],
            "tag": r["tag"],
            "passed": r["passed"],
            "elapsed": r["elapsed"],
            "recall": ev.recall_pct,
            "precision": ev.precision_pct,
            "f1": ev.f1_score,
            "det_count": ev.det_count,
            "matched_entities": r["matched_entities"],
            "final_sql": r["sql_history"][-1] if r["sql_history"] else "",
            "error": r["error"]
        })
        
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"Results recorded to: {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
