import pytest
import os
from langchain_core.messages import SystemMessage, HumanMessage
from app.memory.semantic_memory import ActionCacheManager
from app.core.context.context_builder import ContextBuilder, ContextPacket

def test_action_cache_normalization_clean_text():
    """验证 ActionCacheManager 对口语修饰、虚词、停用词与标点的归一化清洗能力"""
    manager = ActionCacheManager(cache_file="data/test_action_cache.json")
    
    # 测试口语前缀与标点剥离
    q1 = "请重点排查一下今年退运药品的汇总金额，谢谢！"
    norm1 = manager.normalize_question(q1)
    assert not norm1.startswith("请")
    assert not norm1.startswith("排查")
    assert "，" not in norm1 and "！" not in norm1
    
    q2 = "针对退运药品的汇总金额开展核查："
    norm2 = manager.normalize_question(q2)
    assert not norm2.startswith("针对")
    assert not norm2.startswith("开展")
    assert ":" not in norm2 and "：" not in norm2

def test_action_cache_canonical_lookup_hit():
    """验证 L0.5 规范化指纹直通：不同口语表达能秒级命中同一份缓存"""
    test_cache_file = "data/test_action_cache_temp.json"
    if os.path.exists(test_cache_file):
        os.remove(test_cache_file)
        
    try:
        manager = ActionCacheManager(cache_file=test_cache_file)
        # 录入原始问题与结果
        seed_question = "针对高额异常报销单据开展核查"
        expected_sql = "SELECT bill_id, sum(amount) FROM reimbursement GROUP BY bill_id HAVING sum(amount) > 10000"
        manager.save(seed_question, sql=expected_sql, tasks=["task1"])
        
        # 变体查询 1：增加口语修饰词
        variant_1 = "请帮我排查一下高额异常报销单据！"
        norm_var1 = manager.normalize_question(variant_1)
        hit_1 = manager.canonical_lookup.get(norm_var1)
        assert hit_1 is not None, f"未能通过规范化指纹命中缓存: norm={norm_var1}, expected={manager.normalize_question(seed_question)}"
        assert hit_1["sql"] == expected_sql
        
        # 变体查询 2：不同修饰语
        variant_2 = "调取高额异常报销单据进行统计"
        norm_var2 = manager.normalize_question(variant_2)
        hit_2 = manager.canonical_lookup.get(norm_var2)
        assert hit_2 is not None
        assert hit_2["sql"] == expected_sql
    finally:
        if os.path.exists(test_cache_file):
            os.remove(test_cache_file)

def test_context_builder_static_prefix_and_cache_control():
    """验证 ContextBuilder 的静态大块 DDL 前置策略以及 cache_control 标记的正确生成"""
    cb = ContextBuilder()
    
    packets = [
        ContextPacket(
            content="table fqz_gz_jzsj_all_ql schema definition",
            relevance_score=1.0,
            metadata={"type": "clickhouse_schema", "table_name": "fqz_gz_jzsj_all_ql", "priority": "high"}
        ),
        ContextPacket(
            content="<semantic_alignment_context>\n  <guidance>Dynamic audit guidance</guidance>\n</semantic_alignment_context>",
            relevance_score=0.9,
            metadata={"type": "semantic_alignment"}
        ),
        ContextPacket(
            content="Note step 1 finished",
            relevance_score=1.0,
            metadata={"type": "note_evidence", "priority": "high"}
        )
    ]
    
    original_history = [
        SystemMessage(content="You are an audit expert."),
        HumanMessage(content="Hello")
    ]
    
    structured = cb._structure_into_messages(packets, original_history)
    
    # 查找 GSSC payload 消息
    gssc_msg = next((m for m in structured if "【当前审计黄金上下文载荷" in str(m.content)), None)
    assert gssc_msg is not None, "未找到 GSSC 载荷 SystemMessage"
    
    # 验证显式 cache_control: {"type": "ephemeral"}
    assert hasattr(gssc_msg, "additional_kwargs")
    assert gssc_msg.additional_kwargs.get("cache_control") == {"type": "ephemeral"}
    
    content = str(gssc_msg.content)
    # 验证静态 DDL 出现在动态 semantic_alignment 和 notes 之前
    idx_schema = content.find("<database_schema_context>")
    idx_alignment = content.find("<semantic_alignment_context>")
    idx_notes = content.find("<structured_audit_notes>")
    
    assert idx_schema != -1, "缺少 database_schema_context"
    assert idx_alignment != -1, "缺少 semantic_alignment_context"
    assert idx_notes != -1, "缺少 structured_audit_notes"
    
    # 静态在前，动态在后（字节级前缀稳定对齐）
    assert idx_schema < idx_alignment, "静态 DDL 必须排在动态 semantic_alignment 之前以保障前缀缓存命中"
    assert idx_schema < idx_notes, "静态 DDL 必须排在 notes 之前以保障前缀缓存命中"
