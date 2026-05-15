"""
app/core/skill_protocol.py
==========================
[V157.0] 统一技能协议 (Universal Skill Protocol)

规范工具(Skills)的输出结构，使其具备自解释能力，并为审计报告提供底层证据。
"""

from typing import Any, Optional, Dict, List, Literal
from pydantic import BaseModel, Field

class SkillResponse(BaseModel):
    """
    标准技能响应：所有 Agent 工具必须返回此结构的 JSON 或对象。
    """
    status: Literal["SUCCESS", "PARTIAL", "FAILED"] = "SUCCESS"
    data: Any = None                # 业务核心数据 (如 SQL 结果列表)
    logic_summary: str = ""         # 业务逻辑解释 (用于消息生成)
    
    # --- 审计追踪元数据 ---
    trace_hint: str = ""            # 物理执行 ID (如 ClickHouse Query ID)
    schema_version: str = "v1.0"    # 执行时使用的数据库版本
    affected_rows: int = 0          # 涉及的数据行数
    security_verified: bool = True  # 是否通过了安全校验
    error_detail: Optional[str] = None # 错误详情

    def to_chat_summary(self) -> str:
        """生成供 LLM 阅读的简短摘要"""
        if self.status == "FAILED":
            return f"❌ 执行失败: {self.error_detail}"
        return f"✅ 执行成功。扫描到 {self.affected_rows} 条记录。逻辑摘要: {self.logic_summary}"

    def to_audit_dict(self) -> Dict[str, Any]:
        """生成供审计存储的字典"""
        return self.model_dump(exclude={"data"}) # 排除大数据集，仅保留凭证
