"""
将四层认知记忆流程真实写入本地 PostgreSQL 数据库演示脚本
"""

import sys
import os
import asyncio
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 加载 .env
load_dotenv()

from langgraph.graph import StateGraph, END
from app.core.checkpointer import create_checkpointer, CheckpointerBackend
from app.core.memory.types.working import WorkingMemory
from app.core.memory.pii_scrubber import pii_scrubber


class MockAuditState(dict):
    pass


def planner_node(state):
    print("   [Graph] ---> 节点 1 (PLANNER): 读取规则，生成审计 SQL...")
    return {
        "sql_query": "SELECT fixmedins_code, COUNT(*) as cnt FROM oprn_fee WHERE hilist_code LIKE 'XA02BA%' GROUP BY 1;",
        "findings_count": 148,
    }


def reporter_node(state):
    print("   [Graph] ---> 节点 2 (REPORTER): 汇总形成最终审计底稿...")
    return {
        "report_content": f"【市一医院促红素EPO核查底稿】查实 148 条违规处方，违规金额 42.6 万元。"
    }


def build_live_graph():
    wf = StateGraph(dict)
    wf.add_node("PLANNER", planner_node)
    wf.add_node("REPORTER", reporter_node)
    wf.set_entry_point("PLANNER")
    wf.add_edge("PLANNER", "REPORTER")
    wf.add_edge("REPORTER", END)
    return wf


async def main():
    pg_uri = os.getenv("POSTGRES_URI")
    print("\n" + "=" * 70)
    print("🐘 正在连接真实 PostgreSQL 数据库进行物理写入...")
    print(f"目标 URI: {pg_uri}")
    print("=" * 70)

    SESSION_ID = "session_hsa_audit_live_demo_001"
    config = {"configurable": {"thread_id": SESSION_ID}}

    # 1. 使用真实 PostgreSQL 连接池创建 Checkpointer
    async with create_checkpointer(backend=CheckpointerBackend.POSTGRES) as saver:
        graph = build_live_graph().compile(checkpointer=saver)
        
        print("\n▶️ [1] 正在执行工作流并将检查点写入 PostgreSQL...")
        result = await graph.ainvoke({"user_query": "查市一医院EPO违规开药"}, config=config)
        print("   ✅ 工作流执行完毕！底稿结果:", result.get("report_content"))

    # 2. 直连 PostgreSQL 验证写入的物理数据行
    print("\n▶️ [2] 正在直连 PostgreSQL 验证真实物理存储...")
    import psycopg
    conn = psycopg.connect(pg_uri)
    cur = conn.cursor()

    cur.execute("SELECT thread_id, checkpoint_id, parent_checkpoint_id, metadata FROM checkpoints WHERE thread_id = %s;", (SESSION_ID,))
    rows = cur.fetchall()
    print(f"\n📊 【checkpoints 表】已持久化 {len(rows)} 个历史检查点快照:")
    for r in rows:
        print(f"   - 会话ID: {r[0]} | 检查点ID: {r[1]} | 父版本: {r[2]} | 元数据步骤: {r[3].get('step')}")

    cur.execute("SELECT thread_id, channel, version, type FROM checkpoint_blobs WHERE thread_id = %s;", (SESSION_ID,))
    blob_rows = cur.fetchall()
    print(f"\n📦 【checkpoint_blobs 表】已持久化 {len(blob_rows)} 个 State 状态 Channel 二进制快照:")
    for b in blob_rows:
        print(f"   - 会话ID: {b[0]} | Channel状态槽: {b[1]} | 版本: {b[2]} | 序列化格式: {b[3]}")

    cur.execute("SELECT thread_id, checkpoint_id, channel, idx FROM checkpoint_writes WHERE thread_id = %s;", (SESSION_ID,))
    writes_rows = cur.fetchall()
    print(f"\n✍️ 【checkpoint_writes 表】已持久化 {len(writes_rows)} 条节点写入记录 (BSP 超步 Writes):")
    for w in writes_rows:
        print(f"   - 会话ID: {w[0]} | 检查点ID: {w[1]} | 写入Channel: {w[2]} | 步骤Index: {w[3]}")

    conn.close()
    print("\n" + "=" * 70)
    print("🎉 物理验证成功！你现在可以在数据库客户端里查询 checkpoints 表了！")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
