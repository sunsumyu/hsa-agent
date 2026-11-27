"""
[Martin Fowler TDD - 红灯测试 (Red Test)]
测试目标：治理 consolidator_agent.py 中对全局 God State 的无节制隐式依赖。

按照 Matt Pocock 规范：
1. 提取明确的强类型契约 ConsolidationPayload，收缩数据范围。
2. 消除 Feature Envy：节点不再需要从混乱的全局大字典中硬翻字段。
3. 当前该类型与纯函数契约尚未引入，测试预期出现红灯 [RED]！
"""
import pytest

def test_consolidation_payload_contract_exists():
    # 尝试从 consolidator_agent 导入强类型契约
    from app.agents.consolidator_agent import ConsolidationPayload, extract_consolidation_payload
    
    sample_state = {
        "tasks": ["排查超量开药"],
        "sql_query": "SELECT * FROM fqz_fymx_test WHERE cnt > 100",
        "methodology": "核查单次处方超量",
        "current_turn_query": "排查超量开药情况",
        "raw_data": "[{'psn_no': '123'}]",
    }
    
    payload = extract_consolidation_payload(sample_state)
    assert isinstance(payload, ConsolidationPayload)
    assert payload.user_input == "排查超量开药情况"
    assert payload.tasks == ["排查超量开药"]
    assert payload.is_successful is True

def test_consolidation_payload_identifies_failure():
    from app.agents.consolidator_agent import ConsolidationPayload, extract_consolidation_payload
    
    failure_state = {
        "tasks": ["排查"],
        "sql_query": "SELECT 1",
        "error_log": "Syntax error",
        "raw_data": "",
    }
    payload = extract_consolidation_payload(failure_state)
    assert payload.is_successful is False
