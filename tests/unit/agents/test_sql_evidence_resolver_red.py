import pytest
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.sql_evidence_resolver import resolve_core_audit_sql, resolve_user_query


def test_resolve_core_audit_sql_prioritizes_metric_query():
    """测试优先挑选含有金额/计数聚合的核心指标对碰 SQL"""
    history_sql = [
        "SELECT DISTINCT med_type FROM fqz_gz_jzsj_all_ql",  # 探针
        "SELECT psn_no, setl_id FROM fqz_gz_jzsj_all_ql WHERE med_type = '门诊'", # 普通查询
        "SELECT psn_no, sum(medfee_sumamt) AS total_fee FROM fqz_gz_jzsj_all_ql GROUP BY psn_no", # 核心指标
    ]
    def mock_is_probe(sql: str) -> bool:
        return "DISTINCT med_type" in sql

    chosen = resolve_core_audit_sql(history_sql, is_probe_fn=mock_is_probe)
    assert "sum(medfee_sumamt)" in chosen


def test_resolve_core_audit_sql_fallback_to_last_non_probe():
    """测试若无聚合指标，则回退到最后一条非探针业务查询"""
    history_sql = [
        "SELECT * FROM fqz_admdvs LIMIT 5",  # 探针
        "SELECT psn_no, dise_name FROM fqz_gz_jzsj_all_ql WHERE gend = '1'", # 业务查询
    ]
    def mock_is_probe(sql: str) -> bool:
        return "LIMIT 5" in sql

    chosen = resolve_core_audit_sql(history_sql, is_probe_fn=mock_is_probe)
    assert chosen == "SELECT psn_no, dise_name FROM fqz_gz_jzsj_all_ql WHERE gend = '1'"


def test_resolve_core_audit_sql_empty_and_all_probes():
    """测试空列表和全部为探针时的保底行为"""
    assert resolve_core_audit_sql([]) == ""

    all_probes = ["SELECT 1", "SELECT 2"]
    chosen = resolve_core_audit_sql(all_probes, is_probe_fn=lambda _: True)
    assert chosen == "SELECT 2"


def test_resolve_user_query_priority():
    """测试用户意图解析优先级：current_turn_query > metadata > messages 倒序"""
    # 优先级 1: current_turn_query
    state1 = {
        "current_turn_query": "当前轮最新命题",
        "metadata": {"user_question": "初始提问"},
        "messages": [HumanMessage(content="最早问题")]
    }
    assert resolve_user_query(state=state1) == "当前轮最新命题"

    # 优先级 2: metadata.user_question
    state2 = {
        "metadata": {"user_question": "元数据问题"},
        "messages": [HumanMessage(content="历史问题")]
    }
    assert resolve_user_query(state=state2) == "元数据问题"

    # 优先级 3: messages 倒序中的 HumanMessage / tuple / dict
    state3 = {
        "messages": [
            HumanMessage(content="第一个问题"),
            AIMessage(content="回答1"),
            ("human", "第二个问题(tuple)"),
            AIMessage(content="回答2"),
        ]
    }
    assert resolve_user_query(state=state3) == "第二个问题(tuple)"


def test_resolve_user_query_with_fallback_keys():
    """测试当无 messages 且无 metadata.user_question 时，通过 fallback_keys 正确提取提问"""
    state = {
        "human_input": "通过 human_input 传入的审计提问"
    }
    extracted = resolve_user_query(state=state, fallback_keys=["user_query", "human_input", "question"])
    assert extracted == "通过 human_input 传入的审计提问"

