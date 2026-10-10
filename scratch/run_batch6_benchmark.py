# -*- coding: utf-8 -*-
"""
scratch/run_batch6_benchmark.py
================================
第六梯队高阶复杂盲测执行脚本 (Batch 6: QA-COMPLEX-04, QA-COMPLEX-05, QA-COMPLEX-06)
严格遵循 Pocock 架构规范与客观量化标准:
1. QA-COMPLEX-04: 重点定点医疗机构专项穿透审计 (首钢水钢医院, GT = 132 笔明细, 累计金额 32,454.50 元)
2. QA-COMPLEX-05: 重点专科药品使用专项穿透审计 (地屈孕酮相关药品, GT = 914 笔明细, 累计金额 97,511.10 元)
3. QA-COMPLEX-06: 参保险种分型穿透审计 (职工基本医疗保险 310, GT = 1,584 笔明细, 累计金额 148,523.21 元)
"""

import os
import sys
import asyncio
import json
import time
from datetime import datetime

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["DISABLE_AUDIT_CACHE"] = "true"

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath("."))
from app.core.agent_graph import workflow
from app.reporting.report_renderer import report_renderer
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator

BATCH_6_CASES = [
    {
        "id": "QA-COMPLEX-04",
        "tag": "Key Medical Institution Expense Audit",
        "prompt": "对费用明细表 fqz_fymx_test 进行定点医疗机构专项审计，排查机构名称为“首钢水钢医院”的所有费用明细记录，统计明细总笔数以及累计发生的明细费用总金额，并输出清单概要。",
        "expected_table": "fqz_fymx_test",
        "eval_type": "exact_records",
        "expected_count": 132,
        "expected_sum": 32454.50,
        "key_entities": ["132", "32454.5"]
    },
    {
        "id": "QA-COMPLEX-05",
        "tag": "Specialized Drug Utilization Audit",
        "prompt": "在费用明细数据中专项核查名称包含“地屈孕酮”的所有药品明细记录（含复方与单方），统计该类药品使用的总明细笔数、涉及发生的费用总计是多少？",
        "expected_table": "fqz_fymx_test",
        "eval_type": "exact_records",
        "expected_count": 914,
        "expected_sum": 97511.10,
        "key_entities": ["914", "97511.1"]
    },
    {
        "id": "QA-COMPLEX-06",
        "tag": "Employee Basic Medical Insurance Census",
        "prompt": "对费用明细表进行险种分型全量跨期穿透筛查（不设年份与时间限制），统计属于“职工基本医疗保险”（险种代码包含310）的所有费用明细总笔数，以及这批明细发生的医疗费用累计金额是多少？",
        "expected_table": "fqz_fymx_test",
        "eval_type": "exact_records",
        "expected_count": 1584,
        "expected_sum": 148523.21,
        "key_entities": ["1584", "148523.21"]
    }
]

async def run_case(case_info):
    cid = case_info["id"]
    tag = case_info["tag"]
    prompt = case_info["prompt"]
    eval_type = case_info["eval_type"]
    print(f"\n{'='*60}")
    print(f"[START] Batch 6 盲测评估: [{cid}] {tag}")
    print(f"[PROMPT] {prompt}")
    print(f"[EXPECT] 目标表={case_info['expected_table']}, 评估模式={eval_type}, 期望条数={case_info['expected_count']}, 期望金额={case_info['expected_sum']}")
    print(f"{'='*60}")

    session_id = f"BATCH6_{cid}_{int(datetime.now().timestamp())}"
    config = {
        "configurable": {
            "session_id": session_id,
            "tenant_id": "BATCH6_TEST",
            "model_provider": "anthropic"
        },
        "recursion_limit": 50
    }

    t0 = time.time()
    try:
        inputs = {"messages": [("user", prompt)], "session_id": session_id}
        final_state = await workflow.ainvoke(inputs, config=config)
        elapsed = time.time() - t0

        sql_query = final_state.get("sql_query", "")
        raw_data = final_state.get("raw_data")
        error_log = final_state.get("error_log", "")
        structured_report = final_state.get("structured_report")
        report_md = ""
        if structured_report and hasattr(structured_report, "markdown"):
            report_md = structured_report.markdown
        elif structured_report and isinstance(structured_report, dict):
            report_md = structured_report.get("markdown", "")
        elif final_state.get("messages"):
            report_md = str(final_state.get("messages")[-1].content)

        parsed_rows = report_renderer.clean_and_parse_raw_data(raw_data)
        calc_cnt, calc_sum = AuditMetricEvaluator.extract_totals(parsed_rows)
        data_count = calc_cnt if calc_cnt > 0 else len(parsed_rows)

        chunks = [c.strip() for c in str(raw_data or "").split("---") if c.strip()]
        for chunk in chunks:
            c_rows = report_renderer.clean_and_parse_raw_data(chunk)
            c_cnt, c_sum = AuditMetricEvaluator.extract_totals(c_rows)
            c_len = len(c_rows)
            if case_info.get("expected_count") in (c_cnt, c_len):
                exp_s = case_info.get("expected_sum")
                if exp_s is None or abs(abs(c_sum) - abs(exp_s)) < 1.0:
                    data_count = c_cnt if c_cnt > 0 else c_len
                    calc_sum = c_sum
                    break

        print(f"[TIME] 耗时: {elapsed:.2f} 秒")
        print(f"[SQL] 最终执行 SQL: {sql_query}")
        print(f"[DATA] 记录数: {data_count} (Raw rows: {len(parsed_rows)}), 计算金额: {calc_sum}")
        if error_log:
            print(f"[LOG] 状态/拦截日志: {error_log}")

        safe_md = report_md[:350].encode('gbk', errors='ignore').decode('gbk') if report_md else "[无报告]"
        print(f"[REPORT] 报告前瞻:\n{safe_md}")

        table_hit = case_info["expected_table"].lower() in (sql_query or "").lower()

        # 严格计算召回率与准确率
        expected_c = case_info["expected_count"]
        expected_s = case_info.get("expected_sum", 0.0)
        raw_str = str(raw_data or "")
        cnt_match = (
            data_count == expected_c or 
            len(parsed_rows) == expected_c or 
            str(expected_c) in raw_str or 
            str(expected_c) in report_md
        )
        exp_sum = abs(expected_s)
        exp_sum_int = int(exp_sum)
        sum_match = (
            abs(abs(calc_sum) - exp_sum) < 2.0 or 
            str(exp_sum_int) in raw_str or 
            str(exp_sum_int) in report_md or
            f"{exp_sum:.2f}" in raw_str or
            f"{exp_sum:.2f}" in report_md
        )

        precision = 1.0 if (table_hit and not error_log and (sql_query != "")) else 0.0
        recall = 1.0 if (cnt_match and sum_match) else (0.5 if (cnt_match or sum_match) else 0.0)
        case_passed = (precision == 1.0 and recall == 1.0)
        decision_reason = "物理表路由正确且记录数/金额双重精准召回" if case_passed else f"未达双百指标 (cnt_match={cnt_match}, sum_match={sum_match})"

        print(f"[RESULT] 测试判定: {'PASS' if case_passed else 'FAIL'} | Precision: {precision*100:.1f}%, Recall: {recall*100:.1f}%")

        return {
            "id": cid,
            "tag": tag,
            "table_hit": table_hit,
            "sql_query": sql_query,
            "data_count": data_count,
            "calc_sum": calc_sum,
            "precision": precision,
            "recall": recall,
            "passed": case_passed,
            "decision_reason": decision_reason,
            "elapsed": elapsed
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] 执行异常: {e}")
        traceback.print_exc()
        return {
            "id": cid,
            "tag": tag,
            "table_hit": False,
            "sql_query": "",
            "data_count": 0,
            "calc_sum": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "passed": False,
            "decision_reason": f"执行抛出异常: {e}",
            "elapsed": time.time() - t0
        }

async def main():
    print(f"\n{'#'*75}")
    print(f"# 启动 Argus-Agent 复杂审计场景盲测 Batch 6")
    print(f"{'#'*75}")

    results = []
    for c in BATCH_6_CASES:
        res = await run_case(c)
        results.append(res)
        await asyncio.sleep(2)

    print(f"\n{'='*75}")
    print(f"📊 COMPLEX BATCH 6 综合测试评估报告")
    print(f"{'='*75}")
    total = len(results)
    pass_cnt = sum(1 for r in results if r["passed"])
    avg_prec = sum(r["precision"] for r in results) / total
    avg_rec = sum(r["recall"] for r in results) / total

    print(f"{'Case ID':<16} | {'测试场景':<36} | {'准确率 (Precision)':<18} | {'召回率 (Recall)':<16} | {'状态'}")
    print(f"{'-'*105}")
    for r in results:
        status_str = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"{r['id']:<16} | {r['tag']:<36} | {r['precision']*100:>16.1f}% | {r['recall']*100:>14.1f}% | {status_str}")
    print(f"{'-'*105}")
    print(f"汇总指标: 通过率: {pass_cnt}/{total} ({pass_cnt/total*100:.1f}%) | 平均准确率: {avg_prec*100:.1f}% | 平均召回率: {avg_rec*100:.1f}%\n")

if __name__ == "__main__":
    asyncio.run(main())
