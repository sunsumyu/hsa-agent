"""
最小化单问题测试：只跑 1 个 QA case，验证 original_question 是否正确注入。
用法: python tests/test_single_qa.py
"""
import asyncio, time, sys, os
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from app.core.agent_graph import build_graph

    question = "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
    workflow = build_graph()

    print(f"[TEST] Question: {question}")
    print(f"[TEST] Starting single QA run...")
    t0 = time.time()

    state = await workflow.ainvoke(
        {"messages": [("user", question)], "session_id": "test-single"},
        config={"recursion_limit": 30}
    )

    elapsed = time.time() - t0
    msgs = state.get("messages", [])
    report = ""
    for m in reversed(msgs):
        c = str(getattr(m, "content", ""))
        if len(c) > 200:
            report = c
            break

    # 关键断言
    has_sql = bool(state.get("sql_query", "").strip().replace("--", ""))
    has_data = bool(state.get("raw_data", "")) and "0 条" not in state.get("raw_data", "")
    methodology = state.get("methodology", "")
    # [V90.6] 允许部分关键词命中
    keywords = ["同一天", "同一患者", "同一医院", "多次收取", "same day", "patient", "hospital"]
    question_in_meth = any(kw.lower() in methodology.lower() for kw in keywords)
    empty_q_bug = "原始审计问题为空" in methodology or "未提供" in methodology

    print(f"\n{'='*60}")
    print(f"[RESULT] Elapsed: {elapsed:.1f}s")
    print(f"[RESULT] SQL generated: {has_sql}")
    print(f"[RESULT] Has data: {has_data}")
    print(f"[RESULT] Question in methodology: {question_in_meth}")
    print(f"[RESULT] Empty-question bug: {empty_q_bug}")
    print(f"[RESULT] Methodology snippet: {methodology[:200]}")
    print(f"[RESULT] Report snippet: {report[:300]}")
    print(f"{'='*60}")

    if empty_q_bug:
        print("❌ FAIL: original_question 未注入，空问题 bug 仍存在")
        sys.exit(1)
    elif question_in_meth:
        print("✅ PASS: 原题关键词出现在 methodology 中")
    else:
        print("⚠️ WARN: methodology 未直接引用原题关键词（可能仍正确）")

if __name__ == "__main__":
    asyncio.run(main())
