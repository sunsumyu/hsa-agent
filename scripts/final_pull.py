import sys
import asyncio
import json
from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage

async def force_pull():
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except: pass
    print("START: Force Extraction Mode (Case 1-3)...")
    executor, config = get_graph_executor()
    
    test_cases = [
        "查询 P99999 在 2026年1月的门诊报销情况，看是否存在异常。",
        "分析某医院是否存在‘分解住院’的嫌疑，请调取 2025年12月的数据事实。",
        "核算该统筹区由于‘重复检查’造成的医保基金损失金额。"
    ]
    
    results = []
    
    for i, cmd in enumerate(test_cases):
        print(f"\n--- 推演 Case {i+1} ---")
        try:
            state = {
                "messages": [HumanMessage(content=cmd)],
                "findings": [],
                "retry_count": 0,
                "model_id": "qwen-max"
            }
            # 同步调用，强制获取输出
            res_state = await executor.ainvoke(state)
            ans = res_state["messages"][-1].content
            print(f"Result {i+1} Captured!")
            results.append({
                "case": i+1,
                "input": cmd,
                "output": ans,
                "findings": res_state.get("findings", [])
            })
        except Exception as e:
            print(f"Case {i+1} Failed: {e}")

    # 存入物理文件
    with open("data/raw_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n✅ 推演完成！原始数据已存入 data/raw_audit_results.json")

if __name__ == "__main__":
    asyncio.run(force_pull())
