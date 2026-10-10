"""
app/core/tool_engine/models.py
==============================
[V200.0] 强类型工具契约与结构化输入输出规范 (Pydantic Contract Seam)。
彻底消除 prompt 自由文本格式乞求与脆弱正则解析。
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ─── 1. 工具入参规范 (Input Schemas) ───────────────────────────────────────────

class ExecuteAuditSqlInput(BaseModel):
    """执行 ClickHouse 审计 SQL 查询工具的标准入参规范。"""
    sql: str = Field(
        ...,
        description="待执行的 ClickHouse 审计 SQL 语句。必须为只读 SELECT 或 WITH ... SELECT 查询。"
    )
    db_type: str = Field(
        default="clickhouse",
        description="目标数据库类型，默认 clickhouse。"
    )
    purpose: Optional[str] = Field(
        default="",
        description="本次 SQL 查询的业务审计目的摘要。"
    )

    @field_validator("sql")
    @classmethod
    def validate_sql_readonly(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("SQL 不能为空")
        upper = clean.upper()
        if not (upper.startswith("SELECT") or upper.startswith("WITH") or upper.startswith("EXPLAIN") or upper.startswith("SHOW")):
            raise ValueError(f"安全拦截：只允许只读查询语句 (SELECT/WITH)，禁止 DDL/DML 操作: {clean[:40]}...")
        return clean


class AuditMedicalRuleInput(BaseModel):
    """执行静态规则引擎计算的标准入参规范。"""
    rule_id: str = Field(
        ...,
        description="预定义的规则 ID (如 HIGH_FREQ_DRUG_PURCHASE, MALE_IUD, GENDER_CONFLICT 等)。"
    )
    extra_filters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="规则附加动态过滤参数。"
    )


class RunAnomalyDetectionInput(BaseModel):
    """运行离群点与统计异常算法的标准入参规范。"""
    algorithm_id: str = Field(
        ...,
        description="算法标识 (如 zscore, iqr, isolation_forest)。"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="算法动态参数。"
    )


class SubmitAuditPlanInput(BaseModel):
    """
    审计规划器 (Planner) 的结构化输出工具/契约。
    替代传统 prompt '### METHODOLOGY\n...### TASKS\n- 任务1...' 的正则分割。
    """
    methodology: str = Field(
        ...,
        description="本次审计任务的方法论与逻辑推理链条。"
    )
    tasks: List[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="解耦出的原子审计任务动作列表（按执行顺序编排）。"
    )
    target_tables: List[str] = Field(
        default_factory=list,
        description="本轮规划预期检索的物理核心表名列表。"
    )


# ─── 2. 工具调用请求与结果规范 (Tool Calling & Results) ──────────────────────────

class ToolCallRequest(BaseModel):
    """对齐 OpenAI / MCP 标准的统一工具调用请求结构。"""
    call_id: str = Field(default="call_default")
    tool_name: str = Field(..., description="调用的工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具入参字典")


class ToolResult(BaseModel):
    """
    统一工具执行结果：由 ToolEngine 深度模块保证永不崩溃、类型确定的不可变凭据。
    """
    call_id: str
    tool_name: str
    is_success: bool
    data: Any = None                         # 业务证据载荷 (经过结构化有界采样，防 Token 溢出)
    record_count: int = 0                    # 真实命中的底层记录总数
    error_type: Optional[str] = None         # VALIDATION_ERROR | SECURITY_VIOLATION | EXECUTION_ERROR
    error_message: Optional[str] = None      # 用户或模型可读的错误详情
    structured_hints: List[str] = Field(     # 供反思纠错智能体精确自愈的结构化元数据提示
        default_factory=list
    )
    evidence_fingerprint: str = ""           # 结果集与执行环境的幂等内容指纹
    sql_executed: Optional[str] = None       # 真实物理执行的 SQL 逻辑 (经过 AST 重写后)

    def to_summary_text(self) -> str:
        """生成供 Agent 上下文消费的安全简短文本摘要"""
        if not self.is_success:
            hints_str = f" [纠错指引: {'; '.join(self.structured_hints)}]" if self.structured_hints else ""
            return f"❌ 工具 [{self.tool_name}] 执行失败: {self.error_message}{hints_str}"
        return f"✅ 工具 [{self.tool_name}] 成功命中 {self.record_count} 条记录。指纹: {self.evidence_fingerprint[:8]}"
