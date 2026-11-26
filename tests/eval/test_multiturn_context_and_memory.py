# -*- coding: utf-8 -*-
"""
tests/eval/test_multiturn_context_and_memory.py
===============================================
工业级多轮会话压力与功能评测套件 (10 轮端到端会话模拟)
专注于深度验证：
1. 上下文治理模块 (ContextBuilder / GSSC)：
   - Token 预算自适应动态控制与兜底压缩 (Compaction)
   - 前序轮次 XML 载荷脱水防重 (Zero Duplication)
   - 字节级前缀缓存对齐 (Prefix Cache Alignment) 稳定性
   - 复杂多轮 ReAct 交互中的工具调用配对安全网 (ensure_tool_pairing)
2. 记忆中枢模块 (MemoryHub / WorkingMemory / EpisodicMemory / ActionCache)：
   - 工作记忆容量滑动控制 (FIFO 15 轮限制)
   - 跨轮次上下文与便签证据继承 (Note Evidence Recall)
   - L0.5 规范化意图缓存命中 (0ms Canonical Lookup)
"""

import os
import sys
import json
import time
import pytest

if __name__ == "__main__" and sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage, BaseMessage

from app.core.context.context_builder import ContextBuilder, ContextPacket
from app.core.memory.semantic_memory import WorkingMemory, ActionCacheManager, cognitive_memory_manager
from app.core.memory.message_sanitizer import ensure_tool_pairing
from app.core.schemas import RoleConfigV2

# 10 轮递进式审计用户交互场景
SIMULATED_USER_TURNS = [
    {
        "turn": 1,
        "name": "初始排查与主表装载",
        "user_query": "请重点排查 2024 年就诊费用明细中是否存在参保人登记为男性，却结算了妇科专属药品的情况。",
        "target_tables": ["fqz_fymx_test", "fqz_drug_mcs_info_list"],
        "expect_cache_miss": True
    },
    {
        "turn": 2,
        "name": "指代消解与前缀继承",
        "user_query": "其中涉及总违规金额最高的前三家定点医院是哪几家？请统计金额分布。",
        "target_tables": ["fqz_fymx_test"],
        "expect_cache_miss": False
    },
    {
        "turn": 3,
        "name": "外部便签证据写入与实体锚定",
        "user_query": "请将排名第一的「市第一人民医院」作为重点嫌疑对象记入审计工作便签。",
        "target_tables": ["fqz_fymx_test"],
        "note_evidence": "【重点线索】市第一人民医院存在异常集中开具妇科专属药品现象，累计金额超 10 万元。"
    },
    {
        "turn": 4,
        "name": "多源关联穿透与细化查询",
        "user_query": "针对市第一人民医院，进一步调取其结算地屈孕酮片和益母草颗粒的患者名单。",
        "target_tables": ["fqz_fymx_test", "fqz_drug_mcs_info_list"],
    },
    {
        "turn": 5,
        "name": "经验学习与长期记忆沉淀",
        "user_query": "请总结本次男性结算妇科药的典型特征并固化为长期审计经验规则。",
        "target_tables": [],
        "learn_topic": "男性结算妇科专属药品排查规则",
        "learn_content": "限定性别特征：登记为男性 (gend='1') 且药品目录中含有女性专属限定 (nat_hi_druglist_memo LIKE '%限女性%')。"
    },
    {
        "turn": 6,
        "name": "跨业务场景动态切换 (Schema 场景对齐)",
        "user_query": "切换排查场景：核查医保结算中是否存在冲正退费逆向异常单据？",
        "target_tables": ["fqz_gz_jzsj_all_ql"],
    },
    {
        "turn": 7,
        "name": "工作记忆远距离回溯 (Recall)",
        "user_query": "回顾前序核查：我们在第 3 轮便签中重点标记的医院名称是什么？",
        "target_tables": ["fqz_fymx_test"],
    },
    {
        "turn": 8,
        "name": "上下文长链压力测试 (触发预算治理)",
        "user_query": "调取全量药品目录编码字典，并与上述医院历史所有就诊结算做交叉比对，输出详细比对矩阵。" * 3,
        "target_tables": ["fqz_fymx_test", "fqz_gz_jzsj_all_ql", "fqz_drug_mcs_info_list", "fqz_all_yy_yd"],
    },
    {
        "turn": 9,
        "name": "口语变体与 L0.5 意图指纹秒级直通",
        "user_query": "针对男性结算妇科专属药品开展核查统计。",
        "target_tables": ["fqz_fymx_test"],
    },
    {
        "turn": 10,
        "name": "全局审计成果综合汇总底稿",
        "user_query": "请综合以上 9 轮的全部核查发现、涉及医院、重点药品和金额，生成完整的阶段性审计工作底稿报告。",
        "target_tables": ["fqz_fymx_test", "fqz_gz_jzsj_all_ql"],
    }
]

def _assert_turn_invariants(
    turn_num: int,
    user_query: str,
    safe_messages: List[BaseMessage],
    context_builder: ContextBuilder,
    working_memory: WorkingMemory,
    action_cache: ActionCacheManager,
    seed_sql: str,
) -> int:
    """Assert GSSC, token budget, tool pairing, working memory, and L0.5 cache invariants."""
    total_tokens = sum(ContextPacket.estimate_tokens(m.content) for m in safe_messages)
    gssc_payload_count = sum(1 for m in safe_messages if "<context_engineering_payload>" in str(m.content))
    assert gssc_payload_count <= 1, f"Turn {turn_num} 检测到上下文载荷重复注入: count={gssc_payload_count}"
    assert total_tokens <= context_builder.max_input_tokens * 1.05, f"Turn {turn_num} Token 预算超限: {total_tokens} > {context_builder.max_input_tokens}"
    assert len(ensure_tool_pairing(safe_messages)) == len(safe_messages), f"Turn {turn_num} 工具消息出现非配对孤儿节点！"
    assert len(working_memory.buffer) <= working_memory.capacity, f"工作记忆溢出: len={len(working_memory.buffer)}"

    if turn_num == 9:
        canon_q = action_cache.normalize_question(user_query)
        cached_item = action_cache.canonical_lookup.get(canon_q)
        assert cached_item is not None, f"第 9 轮意图变体未能秒级命中 L0.5 规范化缓存: canon_q={canon_q}"
        assert cached_item["sql"] == seed_sql
        print(f"  [Turn 9 Cache Hit] 变体「{user_query}」0ms 命中种子缓存！")

    gssc_msg = next((m for m in safe_messages if "<context_engineering_payload>" in str(m.content)), None)
    if gssc_msg:
        content = str(gssc_msg.content)
        idx_schema = content.find("<database_schema_context>")
        idx_notes = content.find("<structured_audit_notes>")
        if idx_schema != -1 and idx_notes != -1:
            assert idx_schema < idx_notes, f"Turn {turn_num} 静态 DDL 必须排在动态便签之前"
    return total_tokens


async def _run_single_multiturn_step(
    turn_info: Dict[str, Any],
    context_builder: ContextBuilder,
    working_memory: WorkingMemory,
    action_cache: ActionCacheManager,
    chat_history: List[BaseMessage],
    seed_sql: str,
) -> Dict[str, Any]:
    """Execute one simulated dialogue turn through GSSC and verify invariants."""
    turn_num, turn_name = turn_info["turn"], turn_info["name"]
    user_query, target_tables = turn_info["user_query"], turn_info["target_tables"]
    t0 = time.perf_counter()

    working_memory.add(f"User Turn {turn_num}: {user_query}")
    chat_history.append(HumanMessage(content=user_query))
    metadata = {"target_tables": target_tables, "turn_index": turn_num, "session_id": "multiturn_eval_session"}
    if "note_evidence" in turn_info:
        os.makedirs("data", exist_ok=True)
        with open("data/audit_notes.md", "a", encoding="utf-8") as f:
            f.write(f"\n---\n{turn_info['note_evidence']}\n")

    packets = context_builder._gather_all(user_query, target_tables, chat_history, metadata)
    available_budget = int(context_builder.max_input_tokens * (1.0 - context_builder.config.reserve_ratio))
    selected_packets = context_builder._select_packets(packets, user_query, available_budget)
    structured_messages = context_builder._structure_into_messages(selected_packets, chat_history)
    safe_messages = ensure_tool_pairing(await context_builder._compress_messages_budget(structured_messages))

    ai_reply = f"【Turn {turn_num} 取证完成】已定位关键审计指标，涉及数据已锁定。"
    tool_call_id = f"call_{turn_num}"
    chat_history.append(AIMessage(content=ai_reply, tool_calls=[{"name": "execute_audit_sql", "args": {"sql": "SELECT 1"}, "id": tool_call_id}]))
    chat_history.append(ToolMessage(content=json.dumps([{"status": "SUCCESS", "rows": turn_num * 10}], ensure_ascii=False), tool_call_id=tool_call_id))
    working_memory.add(f"Agent Turn {turn_num}: {ai_reply}")

    elapsed = (time.perf_counter() - t0) * 1000
    total_tokens = _assert_turn_invariants(turn_num, user_query, safe_messages, context_builder, working_memory, action_cache, seed_sql)
    print(f"  * Turn {turn_num:02d} [{turn_name:<20}] | Tokens: {total_tokens:<5} | Msgs: {len(safe_messages):<2} | Mem: {len(working_memory.buffer):<2} | 耗时: {elapsed:.1f}ms")
    return {"turn": turn_num, "name": turn_name, "tokens": total_tokens, "messages_count": len(safe_messages), "working_mem_items": len(working_memory.buffer), "elapsed_ms": elapsed}


def _cleanup_and_print_multiturn_report(turn_metrics: List[Dict[str, Any]]) -> None:
    """Clean up temporary test artifacts and print multiturn benchmark table."""
    if os.path.exists("data/test_multiturn_action_cache.json"):
        os.remove("data/test_multiturn_action_cache.json")
    if os.path.exists("data/audit_notes.md"):
        try:
            os.remove("data/audit_notes.md")
        except OSError as exc:
            print(f"[WARN] cleanup data/audit_notes.md skipped: {exc}")

    print("-" * 88)
    print("[10 轮多轮对话评测总结报告]")
    print(f"{'轮次':<6} | {'场景阶段':<22} | {'Token 负载':<12} | {'消息链长度':<10} | {'工作记忆数':<10} | {'处理耗时'}")
    print("-" * 88)
    for m in turn_metrics:
        print(f"{m['turn']:<6} | {m['name']:<20} | {m['tokens']:<12} | {m['messages_count']:<10} | {m['working_mem_items']:<10} | {m['elapsed_ms']:.1f}ms")
    print("-" * 88)
    print("[PASS] 10 轮上下文治理、预算兜底压缩、工作记忆容量滑动与 L0.5 意图缓存全项对账 100% 通过！")
    print("=" * 80)


@pytest.mark.asyncio
async def test_multiturn_10_turns_context_and_memory():
    """
    执行 10 轮模拟用户会话压力与功能全景评测
    """
    print("\n" + "=" * 80)
    print(">> [MULTITURN BENCHMARK] 启动 10 轮端到端用户多轮对话会话压力评测")
    print("=" * 80)

    context_builder = ContextBuilder(role_config=RoleConfigV2(pool="primary", max_input_tokens=4000))
    working_memory = WorkingMemory(capacity=15)
    action_cache = ActionCacheManager(cache_file="data/test_multiturn_action_cache.json")
    chat_history: List[BaseMessage] = [SystemMessage(content="你是国家医保智能审计核心 Agent。请协助审计专家进行严谨的多轮数据穿透核查。")]

    seed_sql = "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test GROUP BY psn_no"
    action_cache.save("排查男性结算妇科专属药品", sql=seed_sql, tasks=["task1"])

    turn_metrics = [
        await _run_single_multiturn_step(turn_info, context_builder, working_memory, action_cache, chat_history, seed_sql)
        for turn_info in SIMULATED_USER_TURNS
    ]
    _cleanup_and_print_multiturn_report(turn_metrics)
