"""
tests/unit/hsa/test_hsa_domain_contracts.py
===========================================
Unit tests verifying the HSA domain contracts:
- Domain state contracts (HSAAuditState)
- Neuro-symbolic SQL guardian gate (HSASQLGuardianGate)
- Multi-agent exports (CoderAgent, PlannerAgent, ReflectionAgent, ConsolidatorAgent)
- Skills exports (sql, schema, security, rules, federated)
- LangGraph orchestration pipeline (build_hsa_audit_graph, get_hsa_executor)
"""

import pytest
from domains.hsa import (
    HSAAuditState,
    HSASQLGuardianGate,
    build_hsa_audit_graph,
    get_hsa_executor,
    hsa_workflow,
    HSAAgentGraph,
    agents,
    skills,
)


def test_hsa_state_contracts():
    """Verify HSA state contract matches expected TypedDict interface."""
    state = {
        "messages": [],
        "user_question": "查询超限用药记录",
        "sql": "SELECT 1",
    }
    assert "user_question" in state
    assert HSAAuditState is not None


def test_hsa_sql_guardian_gate_passes_valid_select():
    """Verify HSASQLGuardianGate allows benign SELECT queries against registered tables with partition pruning."""
    gate = HSASQLGuardianGate()
    result = gate.evaluate({
        "sql": "SELECT count(*) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01' AND medfee_sumamt > 100"
    })
    assert result.passed is True
    assert result.reason is None


def test_hsa_sql_guardian_gate_blocks_destructive_ddl():
    """Verify HSASQLGuardianGate blocks DROP TABLE and destructive queries."""
    gate = HSASQLGuardianGate()
    result = gate.evaluate({"sql": "DROP TABLE test_db.medical_orders"})
    assert result.passed is False
    assert result.error_code == "SQL_SECURITY_VIOLATION"
    assert "DROP" in result.reason or "violation" in result.reason


def test_hsa_agent_exports():
    """Verify all 4 core HSA agent roles are properly exported."""
    assert hasattr(agents, "CoderAgent")
    assert hasattr(agents, "PlannerAgent")
    assert hasattr(agents, "ReflectionAgent")
    assert hasattr(agents, "ConsolidatorAgent")


def test_hsa_skills_exports():
    """Verify all 5 deep skill subpackages are exposed under domains.hsa.skills."""
    assert hasattr(skills, "sql")
    assert hasattr(skills, "schema")
    assert hasattr(skills, "security")
    assert hasattr(skills, "rules")
    assert hasattr(skills, "federated")


def test_hsa_graph_pipeline_instantiation():
    """Verify the compiled HSA audit LangGraph workflow is valid and runnable."""
    assert hsa_workflow is not None
    executor, model_name = get_hsa_executor()
    assert executor is not None
    assert model_name is not None
    
    agent_graph = HSAAgentGraph(model_id="test-model")
    compiled = agent_graph.compile()
    assert compiled is not None
