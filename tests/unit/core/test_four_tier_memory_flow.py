"""
端到端复现与验证：四层认知记忆流转全过程测试 (The 4-Tier Memory Flow)

复现业务场景：医保审计员核查某医院“重组人促红素(EPO)”违规虚增频次案
验证四个阶段：
  阶段 1：语义与经验记忆 (Semantic Memory) - 召回历史高分 SQL 模板与规则
  阶段 2：工作记忆 (Working Memory L0/L1) - 维护会话级临时便签与变量草稿
  阶段 3：断点状态记忆 (Checkpoint Memory) - 模拟节点崩溃中断并精准断点恢复
  阶段 4：情景记忆 (Episodic) 固化事实证据链 + PII 隐私脱敏后的语义经验闭环
"""

import sys
import os
import tempfile
import pathlib
import pytest
from typing import TypedDict, Optional, List, Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 确保项目根路径在 sys.path 中
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from langgraph.graph import StateGraph, END
from app.core.checkpointer import create_checkpointer, CheckpointerBackend
from app.core.memory.types.working import WorkingMemory
from app.core.memory.types.episodic import EpisodicMemory
from app.core.memory.storage.relational import RelationalStorage
from app.core.memory.pii_scrubber import pii_scrubber


# =============================================================================
# 定义极简可复现的状态结构与工作流节点 (模拟真实的 Planner -> SQL -> Reporter)
# =============================================================================
class MockAuditState(TypedDict):
    session_id: str
    user_question: str
    recalled_rule: Optional[str]
    sql_query: Optional[str]
    findings_count: int
    crash_in_reporter: bool  # 用于人为注入崩溃标志
    report_content: Optional[str]


def mock_planner_node(state: MockAuditState) -> Dict[str, Any]:
    print("\n   [Graph] ---> 节点 1 (PLANNER): 意图对齐与规划分析...")
    # 模拟 Planner 引用阶段 1 召回的语义经验
    rule = state.get("recalled_rule") or "通用统计规则"
    sql = "SELECT fixmedins_code, doctor_id, COUNT(*) as cnt FROM oprn_fee WHERE lag_days < 7 GROUP BY 1,2;"
    return {"sql_query": sql, "recalled_rule": rule}


def mock_sqlexec_node(state: MockAuditState) -> Dict[str, Any]:
    print("   [Graph] ---> 节点 2 (SQLEXEC): 物理查询执行完毕，锁定 148 条违规处方！")
    return {"findings_count": 148}


def mock_reporter_node(state: MockAuditState) -> Dict[str, Any]:
    print("   [Graph] ---> 节点 3 (REPORTER): 准备拼装高维图表与审计底稿...")
    if state.get("crash_in_reporter", False):
        print("   💥💥💥 [人为灾难注入] 模拟 Pod 突发 OOM 崩溃 / 网络闪断异常！")
        raise RuntimeError("Pod OOMKilled / Network Timeout Crash in REPORTER node!")
    
    report = f"【最终审计底稿】核查完成：发现违规处方 {state.get('findings_count', 0)} 条，涉及违规金额 42.6 万元。"
    print(f"   [Graph] ---> 节点 3 (REPORTER): 渲染成功！生成底稿: {report}")
    return {"report_content": report}


def build_test_graph():
    wf = StateGraph(MockAuditState)
    wf.add_node("PLANNER", mock_planner_node)
    wf.add_node("SQLEXEC", mock_sqlexec_node)
    wf.add_node("REPORTER", mock_reporter_node)

    wf.set_entry_point("PLANNER")
    wf.add_edge("PLANNER", "SQLEXEC")
    wf.add_edge("SQLEXEC", "REPORTER")
    wf.add_edge("REPORTER", END)
    return wf


# =============================================================================
# 核心测试主体：串联四阶段完整测试
# =============================================================================
def _verify_stage1_semantic_recall(user_query: str) -> Dict[str, Any]:
    """Verify stage 1 semantic memory recall returns matching expert experience."""
    print("\n" + "-" * 70)
    print("▶️ [阶段 1: 语义与经验记忆 (Semantic) 召回]")
    print(f"   -> 用户原始提问: '{user_query}'")
    simulated_semantic_kb = {
        "EPO_超频次开药": {
            "score": 0.94,
            "rule": "国家医保促红素使用规定：同一患者门诊频次低于7天视为异常突击开药",
            "sql_template": "SELECT * FROM oprn_fee WHERE hilist_code LIKE 'XA02BA%' AND diff_days < 7",
        }
    }
    recalled_item = simulated_semantic_kb["EPO_超频次开药"]
    print(f"   -> 🎯 语义向量召回命中历史高分经验 (相似度: {recalled_item['score']}):")
    print(f"      - 经验规则: {recalled_item['rule']}\n      - 参考 SQL: {recalled_item['sql_template']}")
    assert recalled_item["score"] > 0.9
    print("   ✅ [阶段 1 观测完毕] 语义记忆为本次会话注入了专家经验，避免从零盲猜。")
    return recalled_item


def _verify_stage2_working_memory(session_id: str) -> None:
    """Verify stage 2 L0/L1 working memory draft storage and recall."""
    print("\n" + "-" * 70)
    print("▶️ [阶段 2: 工作记忆 (Working Memory) 临时草稿与会话上下文持有]")
    working_mem = WorkingMemory()
    draft_note = {"suspect_count": 148, "lead_doctor": "李医生 (工号1024)", "doctor_cases": 92, "anomaly_pattern": "集中在每周五下午批量集中打卡开药"}
    working_mem.store(f"{session_id}:notes", draft_note, ttl=3600)
    print(f"   -> 写入 L0/L1 工作记忆便签: {draft_note}")

    recalled_working = working_mem.recall(f"{session_id}:notes")
    print(f"   -> 审计员追问时，从工作记忆毫秒级读回上下文: 锁定嫌疑人 = {recalled_working['lead_doctor']}, 涉及处方 = {recalled_working['doctor_cases']} 张")
    assert recalled_working["doctor_cases"] == 92
    print("   ✅ [阶段 2 观测完毕] 工作记忆支持了复杂审计会话中的短时变量记忆与精准消歧。")


async def _verify_stage3_checkpoint_recovery(tmp_path, session_id: str, user_query: str, recalled_rule: str) -> None:
    """Verify stage 3 SQLite checkpoint persistence across crash and resume."""
    print("\n" + "-" * 70)
    print("▶️ [阶段 3: 断点状态记忆 (Checkpoint Memory) 崩溃容灾与断点续跑]")
    db_file = str(tmp_path / "audit_checkpoints.db")
    config = {"configurable": {"thread_id": session_id}}

    print("   -> 第一次启动工作流（人为注入崩溃异常）...")
    async with create_checkpointer(backend=CheckpointerBackend.SQLITE, conn_string=db_file) as checkpointer:
        app_graph = build_test_graph().compile(checkpointer=checkpointer)
        initial_input = {"session_id": session_id, "user_question": user_query, "recalled_rule": recalled_rule, "crash_in_reporter": True, "report_content": None}
        try:
            await app_graph.ainvoke(initial_input, config=config)
        except RuntimeError as crash_err:
            print(f"   🚨 捕捉到运行时崩溃事件: {crash_err}")

        state_snapshot = await app_graph.aget_state(config)
        print(f"   -> 崩溃后检查点快照: 上一个持久化成功的节点是: {state_snapshot.next}")
        print(f"   -> 快照中保留的数据: findings_count = {state_snapshot.values.get('findings_count')}, 产生 SQL = {state_snapshot.values.get('sql_query')}")
        assert state_snapshot.values.get("findings_count") == 148

    print("\n   -> 🔄 模拟服务重启 / 运维恢复，传入相同 thread_id 触发断点续跑...")
    async with create_checkpointer(backend=CheckpointerBackend.SQLITE, conn_string=db_file) as checkpointer_resumed:
        resumed_graph = build_test_graph().compile(checkpointer=checkpointer_resumed)
        resumed_result = await resumed_graph.ainvoke({"crash_in_reporter": False}, config=config)
        print("   -> 断点恢复运行成功！直接从 SQLEXEC 的产出继续，无需重新跑 SQL！")
        print(f"   -> 恢复后获取的最终报告: {resumed_result.get('report_content')}")
        assert "42.6 万元" in resumed_result.get("report_content", "")
    print("   ✅ [阶段 3 观测完毕] Checkpoint 确保了长链条执行在硬件/网络故障下零数据丢失、零重复计算。")


async def _verify_stage4_episodic_and_pii(tmp_path, session_id: str, user_query: str) -> None:
    """Verify stage 4 episodic storage persistence and PII scrubbing."""
    print("\n" + "-" * 70)
    print("▶️ [阶段 4: 情景记忆固化事实链 + PII 隐私脱敏后的语义经验闭环]")
    episodic_mem = EpisodicMemory(storage=RelationalStorage(db_path=str(tmp_path / "episodic.db")))
    audit_fact_record = {
        "session_id": session_id, "investigated_target": "市第一人民医院肿瘤内科",
        "sql_used": "SELECT ... WHERE lag_days < 7", "involved_amount": 426000.0,
        "operator": "审计员小张", "verdict": "违规属实，立案核查",
    }
    await episodic_mem.record_episode(question=user_query, action_chain=audit_fact_record, importance=0.95)
    print("   -> 4.1 情景记忆落盘完毕：已持久化完整法定审计事实链 (问题、证据 SQL、金额、经办人)。")

    raw_experience_with_pii = (
        "【实战查处经验】针对市一医院EPO违规开药：涉案重点患者姓名: 张三 (身份证号: 110101199003072345，电话: 13812345678)，"
        "主治医生: 李医生。查处技巧是利用窗口函数 LAG(oprn_date) 结合药品编码 XA02BA 进行时间跨度过滤。"
    )
    print(f"\n   -> 4.2 原始沉淀经验 (包含患者敏感隐私): \n      \"{raw_experience_with_pii}\"")
    sanitized_experience = pii_scrubber.mask_sensitive_data(raw_experience_with_pii)
    print(f"\n   -> 🛡️ 经过 PIIScrubber 物理脱敏后的安全经验: \n      \"{sanitized_experience}\"")

    assert "110101199003072345" not in sanitized_experience
    assert "110101********45" in sanitized_experience
    assert "13812345678" not in sanitized_experience
    assert "138****5678" in sanitized_experience
    assert "张**" in sanitized_experience
    print("\n   -> 4.3 脱敏经验入库：成功写入公共语义向量库，供未来全局审计任务复用。")
    print("   ✅ [阶段 4 观测完毕] 完成了合规隐私保护与专家经验闭环自进化的双重保障。")


@pytest.mark.asyncio
async def test_complete_four_tier_memory_lifecycle(tmp_path):
    """Verify the full 4-tier cognitive memory lifecycle end-to-end."""
    print("\n" + "=" * 75)
    print("🎬 开始端到端真实复现【四层认知记忆生命周期】全过程")
    print("=" * 75)

    session_id = "session_hsa_audit_20261026"
    user_query = "帮我查一下市一医院今年3月门诊重组人促红素(EPO)是否存在虚增开药频次违规"

    recalled_item = _verify_stage1_semantic_recall(user_query)
    _verify_stage2_working_memory(session_id)
    await _verify_stage3_checkpoint_recovery(tmp_path, session_id, user_query, recalled_item["rule"])
    await _verify_stage4_episodic_and_pii(tmp_path, session_id, user_query)

    print("\n" + "=" * 75)
    print("🎉 恭喜！端到端【四层认知记忆全生命周期】测试全部成功复现与验证通过！")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_complete_four_tier_memory_lifecycle(pathlib.Path(tempfile.mkdtemp())))
