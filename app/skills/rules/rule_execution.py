"""
app/skills/rule_execution.py
============================
医保审计专家核查引擎工具 (RuleExecutionSkill)
薄接口设计，方法论元数据与规则别名映射委托至 RuleCatalog 深模块。
"""

from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import BaseTool
from loguru import logger
from app.skills.audit_rules import rule_engine
from app.skills.anomaly_algorithms import anomaly_detector
from app.skills.rule_catalog import rule_catalog
from app.skills.sql_tools import _execute_audit_sql_logic
from app.skills.audit_execution_pipeline import audit_execution_pipeline


class RuleExecutionInput(BaseModel):
    rule_id: str = Field(
        description="The ID or semantic name of the audit rule or anomaly algorithm to run (e.g., 'GENDER_CONFLICT', 'CROSS_HOSPITAL_OVERLAP', 'VIX_ANOMALY_SCAN')."
    )
    extra_filters: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional dynamic filters extracted from the user question."
    )

    @field_validator("extra_filters", mode="before")
    @classmethod
    def coerce_filters(cls, v):
        """LLM 经常传非法类型（int/list 等），统一强转为 Dict[str,str]"""
        if v is None:
            return None
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        return None


class RuleExecutionSkill(BaseTool):
    name: str = "audit_medical_rule"
    description: str = (
        "医保审计专家核查引擎（内置确定性规则与高级统计学算法）。 "
        "【使用场景】：针对“性别不符”、“分解住院”、“重复收费”、“高频购药”等标准违规场景，或者需要进行“变异指数扫描”、“离群值检测”等复杂统计分析时，**必须**调用此工具。 "
        "【优势】：该工具内部封装了行业专家公认的审计方法论、阈值参数和法律合规依据。相比于 LLM 自行生成的 SQL，此工具产生的结果具有更高的业务准确性和法律效力。"
    )
    args_schema: Type[BaseModel] = RuleExecutionInput

    def _run(self, *args, **kwargs):
        raise NotImplementedError("audit_medical_rule 仅支持异步 _arun 调用")

    async def _arun(self, rule_id: str, **kwargs) -> Dict[str, Any]:
        logger.info(f"🔨 [Skill] Executing Rule/Algorithm: {rule_id}")

        # 1. 委托 RuleCatalog 消解目标规则 ID 与方法论
        target_id = rule_catalog.resolve_target_id(rule_id)
        methodology = rule_catalog.get_methodology(target_id)
        tolerance = rule_catalog.get_tolerance(target_id)

        # 2. 依次尝试规则库与算法库生成 SQL
        extra_filters = kwargs.get("extra_filters")
        sql, is_anomaly = audit_execution_pipeline.resolve_query_sql(
            target_id=target_id,
            extra_filters=extra_filters,
            rule_engine_inst=rule_engine,
            anomaly_detector_inst=anomaly_detector,
        )

        if not sql:
            return {"error": f"Rule or algorithm not found: {rule_id}", "evidence_count": 0}

        try:
            # 3. 执行取证 SQL 并应用业务容差
            raw_data = await _execute_audit_sql_logic(sql, return_raw=True, tolerance=tolerance)
            ok, err, normalized_data = audit_execution_pipeline.normalize_evidence_result(raw_data)
            if not ok:
                return {"error": err, "evidence_count": 0}

            report_text = audit_execution_pipeline.format_evidence_report(
                target_id=target_id,
                raw_data=normalized_data,
                is_anomaly=is_anomaly,
                rule_engine_inst=rule_engine,
                anomaly_detector_inst=anomaly_detector,
            )

            return audit_execution_pipeline.assemble_audit_payload(
                report_text=report_text,
                raw_data=normalized_data,
                methodology=methodology,
                sql=sql,
                is_anomaly=is_anomaly,
            )
        except Exception as e:
            logger.error(f"Rule execution error: {e}")
            return {"error": str(e), "evidence_count": 0}
