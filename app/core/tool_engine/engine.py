"""
app/core/tool_engine/engine.py
==============================
[V200.0] 统一工具协议执行引擎深度模块 (Unified ToolEngine Deep Module)。

符合 codebase-design 深度模块原则：
- 极小表面积 (Small Interface): 仅暴露 get_definitions 与 execute。
- 极大实现深度 (Deep Implementation):
  1. Pydantic 强类型入参前置校验；
  2. AST 模式地面化 (SchemaGrounder: 自动映射别名与数仓表)；
  3. 物理安全校验与行政隔离 (SQLGuardian)；
  4. 数据库错误自动自愈 (Code 6 / Code 215)；
  5. 结构化对象安全采样与指纹生成 (ToolEvidenceExtractor 集成)；
  6. 封闭式异常收敛，向模型反思层产出结构化精确提示 (Structured Hints)。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from loguru import logger
from pydantic import BaseModel, ValidationError

from app.core.tool_engine.models import (
    ExecuteAuditSqlInput,
    AuditMedicalRuleInput,
    RunAnomalyDetectionInput,
    SubmitAuditPlanInput,
    ToolCallRequest,
    ToolResult,
)
from app.core.tool_engine.grounder import SchemaGrounder
from app.core.tool_engine.adapters import (
    IDbExecutionAdapter,
    ClickHouseAdapter,
    OpenAIToolAdapter,
    MCPToolAdapter,
)
from app.skills.security import SQLGuardian, SecurityViolationError
from app.core.registry.schema_registry import schema_registry


class ToolEngine:
    """
    深度工具引擎 (Deep Tool Engine)。
    对调用方完全屏蔽底层参数校验、语法修复、物理适配与数据采样的复杂性。
    """

    def __init__(self, db_adapter: Optional[IDbExecutionAdapter] = None):
        # 接收外部注入的适配器（默认 ClickHouseAdapter，测试时使用 FakeDbAdapter）
        self.db_adapter: IDbExecutionAdapter = db_adapter or ClickHouseAdapter()
        
        # 工具注册表：工具名 -> (Pydantic入参类, 工具中文描述)
        self._registry: Dict[str, Tuple[Type[BaseModel], str]] = {
            "execute_audit_sql": (
                ExecuteAuditSqlInput,
                "执行 ClickHouse 物理审计 SQL 查询。支持复杂关联统计与明细分析。"
            ),
            "audit_medical_rule": (
                AuditMedicalRuleInput,
                "调用预定义的医保审计专家规则引擎进行确定性排查。"
            ),
            "run_anomaly_detection": (
                RunAnomalyDetectionInput,
                "执行针对医保流水数据的多维统计与离群点异常检测算法。"
            ),
            "submit_audit_plan": (
                SubmitAuditPlanInput,
                "提交规划器的解耦审计任务动作列表与方法论推理。"
            ),
        }

    # ── 1. 公共接口 (Small Public Interface) ───────────────────────────────────

    def get_definitions(self, dialect: str = "openai", role: str = "all") -> List[Dict[str, Any]]:
        """
        获取当前角色有权访问的标准化工具契约。
        支持 dialect="openai" (Function Calling) 或 dialect="mcp" (Anthropic MCP)。
        """
        results = []
        for name, (model_cls, desc) in self._registry.items():
            if role == "planner" and name != "submit_audit_plan":
                continue
            if role == "coder" and name == "submit_audit_plan":
                continue

            if dialect.lower() == "mcp":
                results.append(MCPToolAdapter.to_mcp_tool(name, desc, model_cls))
            else:
                results.append(OpenAIToolAdapter.to_function_def(name, desc, model_cls))
        return results

    async def execute(
        self,
        tool_call: Union[ToolCallRequest, Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        执行工具调用。
        核心原则：
        1. 永不向上抛出未捕获崩溃，100% 返回确定性的 ToolResult；
        2. 结构化捕获每一类错误并提供明确的自愈指导。
        """
        ctx = context or {}
        
        # 1. 规范化请求结构
        if isinstance(tool_call, dict):
            req_id = tool_call.get("id") or tool_call.get("call_id") or "call_unknown"
            name = tool_call.get("name") or tool_call.get("tool_name") or ""
            args = tool_call.get("args") or tool_call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"sql": args}
            request = ToolCallRequest(call_id=req_id, tool_name=name, arguments=args)
        else:
            request = tool_call

        name = request.tool_name
        if name not in self._registry:
            return ToolResult(
                call_id=request.call_id,
                tool_name=name,
                is_success=False,
                error_type="UNKNOWN_TOOL",
                error_message=f"未识别的工具名称: `{name}`",
                structured_hints=[f"可用工具包括: {list(self._registry.keys())}"]
            )

        model_cls, _ = self._registry[name]

        # 2. Pydantic 强类型参数前置校验 (取代模糊的自然语言解析)
        try:
            validated_args = model_cls(**request.arguments)
        except ValidationError as ve:
            error_details = [f"{err['loc']}: {err['msg']}" for err in ve.errors()]
            logger.warning(f"🛡️ [ToolEngine] 工具入参契约校验失败: {error_details}")
            return ToolResult(
                call_id=request.call_id,
                tool_name=name,
                is_success=False,
                error_type="VALIDATION_ERROR",
                error_message="工具入参不符合类型定义规范",
                structured_hints=error_details
            )

        # 3. 分发到具体执行逻辑
        if name == "execute_audit_sql":
            return await self._execute_sql(request.call_id, validated_args, ctx)
        elif name == "submit_audit_plan":
            return self._handle_submit_plan(request.call_id, validated_args)
        elif name == "audit_medical_rule":
            return await self._execute_rule(request.call_id, validated_args, ctx)
        else:
            return ToolResult(
                call_id=request.call_id,
                tool_name=name,
                is_success=False,
                error_type="UNIMPLEMENTED",
                error_message=f"工具 `{name}` 的执行逻辑正在接入中"
            )

    # ── 2. 内部深度实现逻辑 (Deep Implementation) ──────────────────────────────

    async def _execute_sql(
        self,
        call_id: str,
        params: ExecuteAuditSqlInput,
        context: Dict[str, Any]
    ) -> ToolResult:
        raw_sql = params.sql
        tenant_id = context.get("tenant_id")
        expected_table = context.get("expected_table")

        # 步骤 A: AST 模式地面化 (将 dim_std_admdvs 自动重写为物理真实表 fqz_admdvs)
        grounded_sql, used_tables, ground_hints = SchemaGrounder.ground_sql(raw_sql)

        # 步骤 B: SQLGuardian 物理安全与租户过滤
        try:
            safe_sql = SQLGuardian.validate_sql(
                grounded_sql,
                tenant_id=tenant_id,
                expected_table=expected_table
            )
        except SecurityViolationError as sve:
            logger.error(f"🛡️ [ToolEngine] SQLGuardian 拦截: {sve}")
            return ToolResult(
                call_id=call_id,
                tool_name="execute_audit_sql",
                is_success=False,
                error_type="SECURITY_VIOLATION",
                error_message=str(sve),
                structured_hints=[
                    SchemaGrounder.get_registered_tables_hint(),
                    "注意：所有表必须以合法的物理前缀 (如 fqz_) 开头并已在系统注册。"
                ]
            )
        except Exception as e:
            return ToolResult(
                call_id=call_id,
                tool_name="execute_audit_sql",
                is_success=False,
                error_type="SYNTAX_ERROR",
                error_message=f"SQL 语法或解析异常: {e}",
                structured_hints=["请检查 SQL 的语法闭合与括号配对。"]
            )

        # 步骤 C: 物理适配器执行
        try:
            records = await self.db_adapter.query(safe_sql)
        except Exception as exec_err:
            err_str = str(exec_err)
            logger.warning(f"⚠️ [ToolEngine] 数据库执行报错，尝试自动自愈: {err_str[:120]}")
            
            # 自愈分支 1: Code 6 包含制表符的日期转换
            if "Code: 6" in err_str and "CANNOT_PARSE_TEXT" in err_str:
                from app.skills.sql_tools import _heal_timestamp_tab
                healed_sql = _heal_timestamp_tab(safe_sql)
                if healed_sql != safe_sql:
                    try:
                        records = await self.db_adapter.query(healed_sql)
                        safe_sql = healed_sql
                    except Exception as retry_e:
                        return ToolResult(
                            call_id=call_id,
                            tool_name="execute_audit_sql",
                            is_success=False,
                            error_type="EXECUTION_ERROR",
                            error_message=str(retry_e),
                            sql_executed=healed_sql
                        )
                else:
                    return ToolResult(
                        call_id=call_id,
                        tool_name="execute_audit_sql",
                        is_success=False,
                        error_type="EXECUTION_ERROR",
                        error_message=err_str,
                        sql_executed=safe_sql
                    )
            # 自愈分支 2: Code 215 GROUP BY 漏字段
            elif "Code: 215" in err_str:
                from app.skills.sql_tools import _heal_group_by_215
                healed_sql = _heal_group_by_215(safe_sql, err_str)
                if healed_sql != safe_sql:
                    try:
                        records = await self.db_adapter.query(healed_sql)
                        safe_sql = healed_sql
                    except Exception as retry_e:
                        return ToolResult(
                            call_id=call_id,
                            tool_name="execute_audit_sql",
                            is_success=False,
                            error_type="EXECUTION_ERROR",
                            error_message=str(retry_e),
                            sql_executed=healed_sql
                        )
                else:
                    return ToolResult(
                        call_id=call_id,
                        tool_name="execute_audit_sql",
                        is_success=False,
                        error_type="EXECUTION_ERROR",
                        error_message=err_str,
                        sql_executed=safe_sql
                    )
            # 自愈分支 3: Code 184 别名遮蔽导致 ILLEGAL_AGGREGATION
            elif "Code: 184" in err_str or "ILLEGAL_AGGREGATION" in err_str or "is found in WHERE in query" in err_str:
                from app.core.protocol.tool_normalizer import ToolResponseNormalizer
                healed_sql = ToolResponseNormalizer.fix_shadowing_aliases(safe_sql)
                if healed_sql != safe_sql:
                    try:
                        records = await self.db_adapter.query(healed_sql)
                        safe_sql = healed_sql
                    except Exception as retry_e:
                        return ToolResult(
                            call_id=call_id,
                            tool_name="execute_audit_sql",
                            is_success=False,
                            error_type="EXECUTION_ERROR",
                            error_message=str(retry_e),
                            sql_executed=healed_sql
                        )
                else:
                    return ToolResult(
                        call_id=call_id,
                        tool_name="execute_audit_sql",
                        is_success=False,
                        error_type="EXECUTION_ERROR",
                        error_message=err_str,
                        sql_executed=safe_sql
                    )
            else:
                return ToolResult(
                    call_id=call_id,
                    tool_name="execute_audit_sql",
                    is_success=False,
                    error_type="EXECUTION_ERROR",
                    error_message=err_str,
                    sql_executed=safe_sql
                )

        # 步骤 D: 结构化采样与指纹生成 (集成 ToolEvidenceExtractor)
        total_count = len(records)
        from app.agents.tool_evidence_extractor import ToolEvidenceExtractor
        extractor = ToolEvidenceExtractor(max_chars=12000)
        safe_serialized = extractor.truncate_data(records)

        # 生成确定性内容指纹
        fp_src = f"{safe_sql}_{total_count}_{json.dumps(records[:3] if records else [], sort_keys=True, default=str)}"
        evidence_fp = hashlib.sha256(fp_src.encode("utf-8")).hexdigest()

        all_hints = list(ground_hints)
        if total_count == 0:
            all_hints.append("查询返回 0 条记录。若为核心审计排查，请核对过滤条件是否过于苛刻。")

        return ToolResult(
            call_id=call_id,
            tool_name="execute_audit_sql",
            is_success=True,
            data=records[:50],                # 结构化保证完整的采样记录列表
            record_count=total_count,
            structured_hints=all_hints,
            evidence_fingerprint=evidence_fp,
            sql_executed=safe_sql
        )

    def _handle_submit_plan(self, call_id: str, params: SubmitAuditPlanInput) -> ToolResult:
        """处理结构化 Planner 规划动作"""
        plan_dict = {
            "methodology": params.methodology,
            "tasks": params.tasks,
            "target_tables": params.target_tables
        }
        fp = hashlib.sha256(json.dumps(plan_dict, sort_keys=True).encode("utf-8")).hexdigest()
        return ToolResult(
            call_id=call_id,
            tool_name="submit_audit_plan",
            is_success=True,
            data=plan_dict,
            record_count=len(params.tasks),
            evidence_fingerprint=fp
        )

    async def _execute_rule(
        self,
        call_id: str,
        params: AuditMedicalRuleInput,
        context: Dict[str, Any]
    ) -> ToolResult:
        """调用预定义静态规则引擎"""
        from app.skills.audit_rules import audit_rule_engine
        try:
            res = await audit_rule_engine.execute_rule(params.rule_id, params.extra_filters or {})
            records = res if isinstance(res, list) else (res.get("data") if isinstance(res, dict) else [])
            return ToolResult(
                call_id=call_id,
                tool_name="audit_medical_rule",
                is_success=True,
                data=records[:50],
                record_count=len(records),
                evidence_fingerprint=hashlib.sha256(str(params.rule_id).encode()).hexdigest()
            )
        except Exception as e:
            return ToolResult(
                call_id=call_id,
                tool_name="audit_medical_rule",
                is_success=False,
                error_type="RULE_ERROR",
                error_message=str(e)
            )


# 单例导出
tool_engine = ToolEngine()
