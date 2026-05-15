"""
app/core/permission_manager.py
==============================
[V150.0] 企业级权限管理中心 (RBAC/ABAC)

负责：
1. 角色能力定义：定义不同审计角色（JUNIOR, SENIOR, ADMIN）的可操作范围。
2. 算子访问控制：拦截未授权的工具调用。
3. 数据脱敏策略：根据用户级别决定是否下发原始明细。
"""

from enum import Enum
from typing import Set, Dict, Any, List
from loguru import logger

class AuditRole(Enum):
    JUNIOR = "junior"    # 初级稽核员：只能看常规报表，不能运行高危算法
    SENIOR = "senior"    # 高级稽核员：可运行所有算法，但不能直接写 SQL
    ADMIN  = "admin"     # 管理员：拥有全量权限，包括直接执行 SQL 修复数据

# 能力映射表
CAPABILITIES = {
    AuditRole.JUNIOR: {
        "list_tables", "get_table_schema", "lookup_medical_schema", 
        "check_audit_governance", "search_expert_knowledge", "audit_medical_rule"
    },
    AuditRole.SENIOR: {
        "list_tables", "get_table_schema", "lookup_medical_schema", 
        "check_audit_governance", "search_expert_knowledge", "audit_medical_rule",
        "run_anomaly_detection", "federated_graph_sideloader"
    },
    AuditRole.ADMIN: {
        "*" # 全量权限通配符
    }
}

class PermissionManager:
    def __init__(self):
        # 默认使用 SENIOR 角色
        self.default_role = AuditRole.SENIOR

    def get_user_role(self, user_id: str) -> AuditRole:
        """模拟用户角色获取（实际应从数据库或 JWT 读取）"""
        if "admin" in user_id.lower(): return AuditRole.ADMIN
        if "jr" in user_id.lower(): return AuditRole.JUNIOR
        return self.default_role

    def is_tool_allowed(self, user_id: str, tool_name: str) -> bool:
        """校验用户是否有权调用指定工具"""
        role = self.get_user_role(user_id)
        allowed = CAPABILITIES.get(role, set())
        
        if "*" in allowed: return True
        return tool_name in allowed

    def filter_skills(self, user_id: str, all_skills: List[Any]) -> List[Any]:
        """为特定用户过滤可用的工具列表"""
        filtered = [s for s in all_skills if self.is_tool_allowed(user_id, s.name)]
        if len(filtered) < len(all_skills):
            logger.info(f"🛡️ [Permissions] 为用户 {user_id} 过滤了 {len(all_skills) - len(filtered)} 个越权工具")
        return filtered

# 单例导出
permission_manager = PermissionManager()
