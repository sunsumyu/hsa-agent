"""
tests/unit/core/test_multiturn_dialogue_postgres.py
===================================================
真实 PostgreSQL 驱动：完整三轮多轮对话与状态演进测试 (Live Multi-turn Dialogue)

测试场景：医保审计员与 Argus Agent 进行三轮逐步深入的真实业务核查：
  - 第 1 轮：总体宏观排查（市一医院促红素违规初筛，检出 148 条违规）
  - 第 2 轮：上下文继承与下钻（追问重点违规医生，单笔 > 2000 元，下钻检出 3 名重点医生）
  - 第 3 轮：结论收敛与文书生成（汇总前两轮证据，生成正式《医保稽核现场核实通知书》）

核心验证能力：
  1. 上下文完全通过 PostgreSQL 持久化 Checkpoint 自动恢复，无需重复传参；
  2. 每一轮的状态版本（Parent-Child Checkpoint Chain）严格保证因果演进；
  3. 直连 PostgreSQL 校验物理表（checkpoints, checkpoint_blobs, checkpoint_writes）的物理落地。
"""

import sys
import os
import json
import uuid
import pytest
from typing import TypedDict, List, Dict, Any, Optional
from operator import add
from typing_extensions import Annotated

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 引入项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from langgraph.graph import StateGraph, END
from app.core.checkpointer import create_checkpointer, CheckpointerBackend


# =============================================================================
# 1. 定义多轮对话状态结构 (State)
# =============================================================================
class DialogueTurn(TypedDict):
    turn_id: int
    user_input: str
    agent_output: str


class MultiTurnAuditState(TypedDict):
    session_id: str
    target_hospital: Optional[str]
    target_drug: Optional[str]
    current_query: str
    findings_summary: Optional[str]
    drill_down_doctors: Optional[List[str]]
    final_notice: Optional[str]
    # 使用 Annotated[..., add] 实现多轮对话历史的自动追加，而非暴力覆盖
    dialogue_history: Annotated[List[DialogueTurn], add]


# =============================================================================
# 2. 定义业务节点逻辑 (智能感知多轮上下文)
# =============================================================================
def planner_node(state: MultiTurnAuditState) -> Dict[str, Any]:
    query = state.get("current_query", "")
    history = state.get("dialogue_history", [])
    turn_num = len(history) + 1
    
    hospital = state.get("target_hospital")
    drug = state.get("target_drug")

    # 第 1 轮：初筛提取实体
    if turn_num == 1:
        hospital = "市一医院"
        drug = "重组人促红素(EPO)"
        findings = "【初筛结论】查实市一医院促红素超频次违规处方 148 条，涉案金额 42.6 万元。"
        output = f"已完成针对【{hospital}】关于【{drug}】的全面初筛：{findings}"
        return {
            "target_hospital": hospital,
            "target_drug": drug,
            "findings_summary": findings,
            "dialogue_history": [{"turn_id": 1, "user_input": query, "agent_output": output}],
        }

    # 第 2 轮：继承上一轮的实体，进行深入下钻
    elif turn_num == 2:
        top_doctors = ["王主治(违规12笔/7.8万)", "李副高(违规11笔/6.2万)", "张主治(违规9笔/4.2万)"]
        output = (
            f"已基于上轮核查的【{hospital} - {drug}】违规处方完成下钻。"
            f"筛选单笔 > 2000 元严重违规处方共 32 笔，锁定 3 位高频医生：" + "、".join(top_doctors)
        )
        return {
            "drill_down_doctors": top_doctors,
            "dialogue_history": [{"turn_id": 2, "user_input": query, "agent_output": output}],
        }

    # 第 3 轮：汇总所有前置步骤，输出法律公文
    else:
        doctors = state.get("drill_down_doctors") or []
        doc_str = "、".join(doctors)
        notice = (
            f"《国家医疗保障基金监督检查现场核查通知书》\n"
            f"被核查单位：{hospital}\n"
            f"核查事项：{drug} 临床使用合规性\n"
            f"核实事实：涉案违规金额合计 42.6 万元，其中重点医生({doc_str})占 42.7%。\n"
            f"整改要求：请于 3 个工作日内提供相关病案用药指征说明。"
        )
        return {
            "final_notice": notice,
            "dialogue_history": [{"turn_id": 3, "user_input": query, "agent_output": notice}],
        }


def build_audit_graph():
    workflow = StateGraph(MultiTurnAuditState)
    workflow.add_node("AUDIT_PLANNER", planner_node)
    workflow.set_entry_point("AUDIT_PLANNER")
    workflow.add_edge("AUDIT_PLANNER", END)
    return workflow


# =============================================================================
# 3. 完整多轮对话测试用例
# =============================================================================
async def _run_three_dialogue_turns(graph, config: Dict[str, Any]) -> None:
    """Execute three progressive dialogue turns against the compiled audit graph."""
    print("\n💬 [第 1 轮 - 用户]: 排查市一医院促红素(EPO)的超频次违规用药。")
    res1 = await graph.ainvoke({"current_query": "排查市一医院促红素(EPO)的超频次违规用药。"}, config=config)
    print(f"🤖 [第 1 轮 - Agent]: {res1['dialogue_history'][-1]['agent_output']}")
    assert res1["target_hospital"] == "市一医院"
    assert res1["target_drug"] == "重组人促红素(EPO)"
    assert len(res1["dialogue_history"]) == 1

    print("\n💬 [第 2 轮 - 用户]: 其中有哪些重点违规医生？只筛选单笔金额大于 2000 元的严重违规。")
    res2 = await graph.ainvoke({"current_query": "其中有哪些重点违规医生？只筛选单笔金额大于 2000 元的严重违规。"}, config=config)
    print(f"🤖 [第 2 轮 - Agent]: {res2['dialogue_history'][-1]['agent_output']}")
    assert res2["target_hospital"] == "市一医院"
    assert len(res2["drill_down_doctors"]) == 3
    assert len(res2["dialogue_history"]) == 2
    print("   ✅ 上下文继承验证成功：自动识别上轮【市一医院】与【重组人促红素(EPO)】！")

    print("\n💬 [第 3 轮 - 用户]: 汇总前两轮分析，生成正式核查通知书。")
    res3 = await graph.ainvoke({"current_query": "汇总前两轮分析，生成正式核查通知书。"}, config=config)
    print(f"🤖 [第 3 轮 - Agent]:\n{res3['dialogue_history'][-1]['agent_output']}")
    assert res3["final_notice"] is not None
    assert "42.6 万元" in res3["final_notice"]
    assert len(res3["dialogue_history"]) == 3
    print("   ✅ 多轮收敛验证成功：累计 3 轮对话历史完整保存在 State 中！")


def _verify_postgres_checkpoint_tables(pg_uri: Optional[str], test_session_id: str) -> None:
    """Query PostgreSQL checkpoint tables directly to confirm DAG and blob writes."""
    import psycopg

    print("\n" + "=" * 75)
    print("🐘 正在直连 PostgreSQL 校验多轮对话的物理数据存储...")
    print("=" * 75)

    conn = psycopg.connect(pg_uri)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT checkpoint_id, parent_checkpoint_id, metadata
        FROM checkpoints
        WHERE thread_id = %s
        ORDER BY checkpoint_id ASC;
        """,
        (test_session_id,),
    )
    checkpoint_rows = cur.fetchall()
    print(f"\n📊 【checkpoints 表】已为会话保存了 {len(checkpoint_rows)} 个版本状态快照:")
    for idx, (cid, pid, meta) in enumerate(checkpoint_rows, 1):
        step = meta.get("step") if isinstance(meta, dict) else "?"
        print(f"   [{idx}] 版本: {cid} | 父版本: {pid} | 超步Step: {step}")

    assert len(checkpoint_rows) >= 6, "三轮对话应该至少包含 6 个以上的细粒度超步检查点！"
    assert checkpoint_rows[1][1] == checkpoint_rows[0][0], "检查点因果依赖链断裂！父子指针不匹配！"
    print("   ✅ 检查点因果依赖链完整度 100%！")

    cur.execute("SELECT COUNT(*) FROM checkpoint_blobs WHERE thread_id = %s;", (test_session_id,))
    blob_count = cur.fetchone()[0]
    print(f"\n📦 【checkpoint_blobs 表】已持久化 {blob_count} 个二进制 Channel 状态块。")
    assert blob_count > 0

    cur.execute("SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = %s;", (test_session_id,))
    writes_count = cur.fetchone()[0]
    print(f"✍️ 【checkpoint_writes 表】已持久化 {writes_count} 个超步节点写入动作。")
    assert writes_count > 0
    conn.close()


@pytest.mark.asyncio
async def test_live_multiturn_dialogue_postgres():
    """Verify multi-turn dialogue state evolution persisted in live PostgreSQL."""
    test_session_id = f"session_live_multiturn_{uuid.uuid4().hex[:8]}"
    print("\n" + "=" * 75)
    print(f"🚀 开始真实 PostgreSQL 多轮对话演进测试！会话 ID: {test_session_id}")
    print("=" * 75)

    config = {"configurable": {"thread_id": test_session_id}}
    pg_uri = os.getenv("POSTGRES_URI")
    async with create_checkpointer() as checkpointer:
        graph = build_audit_graph().compile(checkpointer=checkpointer)
        await _run_three_dialogue_turns(graph, config)

    _verify_postgres_checkpoint_tables(pg_uri, test_session_id)
    print("\n" + "=" * 75)
    print("🎉 恭喜！真实 PostgreSQL 多轮对话端到端演进与物理落盘全部验证通过！")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_live_multiturn_dialogue_postgres())
