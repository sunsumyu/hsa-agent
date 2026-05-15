from app.core.registry import skill_registry
from .medical_schema import MedicalSchemaSkill
from .rule_execution import RuleExecutionSkill
from .sql_execution import SQLSafeExecutionSkill
from .federated_query import FederatedAuditSkill

# 1. 注册类定义 Skill [V150.0]
skill_registry.register(MedicalSchemaSkill())
skill_registry.register(RuleExecutionSkill())
skill_registry.register(SQLSafeExecutionSkill())
skill_registry.register(FederatedAuditSkill())

# 2. 注册函数式基础工具 [V150.1]
from app.tools import (
    get_table_schema, list_tables,
    search_expert_knowledge, 
    check_audit_governance, federated_graph_sideloader,
    run_anomaly_detection, calculator
)

core_tools = [
    get_table_schema, list_tables,
    search_expert_knowledge, 
    check_audit_governance, federated_graph_sideloader,
    run_anomaly_detection, calculator
]

for t in core_tools:
    skill_registry.register(t)

def get_audit_tools():
    """获取所有已注册的审计算子"""
    return skill_registry.get_all_skills()

__all__ = [
    "get_audit_tools",
    "skill_registry"
]
