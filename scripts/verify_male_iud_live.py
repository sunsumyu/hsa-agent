import asyncio
import os
import sys

# 环境初始化
sys.path.append(os.getcwd())
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["LANGFUSE_PUBLIC_KEY"] = ""  # 禁用观测以加速单次测试

from app.core.bootstrap import register_services
register_services()

from app.core.agent_graph import get_graph_executor

import time

async def main():
    executor, _ = get_graph_executor()
    question = "请排查男性参保人使用宫内节育器（上环/取环）的违规结算明细，输出涉案人员与金额并统计。"
    session_id = f"LIVE_QA02_{int(time.time())}"
    print("=" * 60)
    print(f"[START LIVE AUDIT] 启动真实 Agent 流水线 (Session: {session_id}):\n  任务: {question}")
    print("=" * 60)
    
    inputs = {
        "messages": [("user", question)],
        "session_id": session_id
    }
    
    final_content = ""
    async for event in executor.astream(inputs, stream_mode="updates"):
        for node_name, output in event.items():
            print(f"  -> 节点 [{node_name}] 完成执行")
            if isinstance(output, dict) and "sql_query" in output and output["sql_query"]:
                print(f"     [SQL 生成/执行]: {output['sql_query'][:120]}...")
            if node_name == "REPORTER":
                if isinstance(output, dict) and "messages" in output and output["messages"]:
                    final_content = output["messages"][-1].content
    
    print("\n" + "=" * 60)
    print("[FINAL AUDIT REPORT] 最终审计执行报告:")
    print("=" * 60)
    if final_content:
        print(final_content)
    else:
        print("未获取到 Reporter 内容。")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
