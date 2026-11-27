import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from app.agents.coder_agent import CoderAgent

def test_coder_preserves_primary_audit_query_when_reflection_probes_follow():
    agent = CoderAgent()
    
    # 模拟状态：首轮执行了复杂业务审计 SQL，次轮触发了空结果自愈探查 SQL
    primary_sql = "WITH cte AS (SELECT psn_no, COUNT(DISTINCT hosp) FROM t GROUP BY psn_no HAVING COUNT(DISTINCT hosp) >= 2) SELECT * FROM cte"
    probe_sql = "SELECT COUNT(*) AS total_rows, MIN(setl_time), MAX(setl_time) FROM t"
    
    assert agent._is_probe_query(probe_sql) is True
    assert agent._is_probe_query(primary_sql) is False
    
    # 验证 selection 机制：当存在探查 SQL 时，core_sql 必须锁定 primary_sql，而非落入 probe_sql
    history_sql = [primary_sql, probe_sql]
    audit_queries = [s for s in history_sql if not agent._is_probe_query(s)]
    assert audit_queries == [primary_sql]
    
    # 进一步验证：如果有带指标的查询，也必须是 audit_queries 范围内的查询
    selected_core = audit_queries[-1] if audit_queries else history_sql[-1]
    assert selected_core == primary_sql

if __name__ == "__main__":
    test_coder_preserves_primary_audit_query_when_reflection_probes_follow()
    print("ALL TESTS PASSED SUCCESSFULLY!")
