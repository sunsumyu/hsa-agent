import asyncio
import os
import json
import time
from loguru import logger
from app.core.agent_graph import get_graph_executor
from app.infra.usage_tracker import usage_tracker

# 2024 生产实战测试用例
PROD_TEST_CASES = [
    {
        "id": 1,
        "name": "高额穿透审计",
        "question": "寻找 2024 年度总医疗费用(medfee_sumamt)排名前 5 的患者，并列出他们的总金额和就医次数。"
    },
    {
        "id": 2,
        "name": "跨院重复结算探测",
        "question": "识别在 2024 年 3 月份，在 3 家及以上不同定点医疗机构产生结算记录的患者清单。"
    },
    {
        "id": 3,
        "name": "单病种金额异常分析",
        "question": "分析 2024 年第一季度，单笔医疗费用超过 10 万元的异常案例，列出患者 ID、金额和就诊医院。"
    },
    {
        "id": 4,
        "name": "机构统筹基金水位监控",
        "question": "统计 2024 年各定点医疗机构的医保统筹基金支付(fund_pay_sumamt)总额，找出排名前三的机构。"
    },
    {
        "id": 5,
        "name": "特定患者全景审计",
        "question": "针对患者 ID '52000001000000003004108338'，深度审计其 2024 年所有的就医记录，分析其是否存在频繁就医或费用异常风险。"
    }
]

async def run_prod_benchmark():
    logger.info("🚀 启动 V37.1 生产实战压力测试 (2024 Data, 2.1M Rows)")
    app, _ = get_graph_executor()
    
    results = []
    total_start = time.time()
    
    for case in PROD_TEST_CASES:
        logger.info(f"\n{'='*60}\n>>> [实战案例 {case['id']}] {case['name']}\n{'='*60}")
        start_time = time.time()
        
        inputs = {"messages": [("user", case["question"])], "retry_count": 0}
        
        try:
            final_state = await app.ainvoke(inputs)
            elapsed = time.time() - start_time
            
            report = final_state.get("messages", [])[-1].content if final_state.get("messages") else "No Report"
            sql = final_state.get("sql_query", "N/A")
            
            logger.info(f">>> [耗时]: {elapsed:.1f}s")
            logger.info(f">>> [SQL]: {sql}")
            
            results.append({
                "id": case["id"],
                "name": case["name"],
                "elapsed": elapsed,
                "sql": sql,
                "report_preview": report[:200] + "..."
            })
            
        except Exception as e:
            logger.error(f"案例 {case['id']} 执行崩溃: {e}")
            results.append({"id": case["id"], "status": "FAILED", "error": str(e)})

    total_elapsed = time.time() - total_start
    
    # 汇总输出
    print("\n" + "="*60)
    print("V37.1 Production Pressure Test Summary")
    print("="*60)
    for res in results:
        status = "[OK]" if "elapsed" in res else "[FAIL]"
        time_str = f"{res['elapsed']:.1f}s" if "elapsed" in res else "N/A"
        print(f"[{res['id']}] {res['name']}: {status} {time_str}")
    print("="*60)
    print(f"Total: {total_elapsed:.1f}s | Avg: {total_elapsed/len(PROD_TEST_CASES):.1f}s")
    
    # 记录 Token 消耗 (由 UsageTracker 自动记录)
    print(usage_tracker.get_usage_report())

if __name__ == "__main__":
    asyncio.run(run_prod_benchmark())
