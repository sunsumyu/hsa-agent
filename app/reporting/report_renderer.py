"""
app/report_renderer.py
======================
[企业级可复用模块] 确定性审计报告渲染器

解决问题：
    让 LLM 生成完整的长篇结构化报告，极易在复杂任务下发生"物理截断"，
    导致报告不完整，Judge 全面扣分。核心矛盾：LLM 擅长语义推理，不擅长
    控制输出长度和结构一致性。

设计思路（来自 Anthropic/Vellum 最佳实践）：
    "将数据过滤、报告拼接等完全交给确定性 Python 代码；
     只让 LLM 负责它最擅长的语义分析。"

五章节分工：
    第一章 审计任务    ← 直接来自 user_question（确定性）
    第二章 核查口径    ← 从 sql_query / table_info 生成（确定性）
    第三章 核查数据发现 ← 从 raw_data 生成 Markdown 表格（确定性）
    第四章 核查结论    ← LLM 输出（仅此处，约 150~300 字）
    第五章 风险评级    ← 从金额/条数阈值计算（确定性）

设计原则：
    - 零业务依赖：不 import 任何审计、医保相关模块
    - 输出可预期：同等输入必然产生同等结构的报告
    - LLM 职责最小化：只有第四章节需要 LLM，其余全部确定性生成

使用方式：
    from app.reporting.report_renderer import AuditReportRenderer

    renderer = AuditReportRenderer()
    report = renderer.render(
        user_question="核查是否存在重复住院...",
        sql_query="SELECT ...",
        raw_data=[{"psn_no": "xxx", "amount": 1234.0}, ...],
        llm_conclusion="经分析，发现 3 名患者存在跨院重复住院行为...",
        total_amount=12500.0,
        finding_count=3,
        policy_basis="《医保基金监管条例》第十五条",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


# ──────────────────────────────────────────────────────────
from app.reporting.policy_matcher import (
    match_policies,
    match_oral_policy,
    build_zero_finding_boundary,
    build_positive_finding_boundary,
    match_visualization,
    build_actionable_steps,
)
from app.core.prompts import CONCLUSION_PROMPT


# 风险等级阈值配置（可在实例化时覆盖）
# ──────────────────────────────────────────────────────────
DEFAULT_RISK_THRESHOLDS = {
    "high": {"min_amount": 50_000, "min_count": 10},
    "medium": {"min_amount": 10_000, "min_count": 3},
    # 低于 medium 阈值则为"低"风险
}

# 每条证据记录展示的最大条数
DEFAULT_MAX_EVIDENCE_ROWS = 10

# 证据表格中不展示的敏感字段（脱敏处理）
SENSITIVE_FIELDS = {"psn_name", "certno", "phone", "addr", "org_name", "fixmedins_name", "id_card", "tel"}


def _format_dynamic_policy_tag(rec: Dict[str, Any]) -> str:
    title = str(rec.get("law_title") or "").strip()
    art = str(rec.get("article_num") or "").strip()
    cid = str(rec.get("citation_id") or "").strip()
    label = f"《{title}》{art}" if title else str(rec.get("source_doc") or "法规条款").strip()
    return f"[向量库实查] {label}（ID: {cid}）"


def _apply_citation_guardrail(
    policy_basis: Optional[str],
    llm_conclusion: str,
    audit_metadata: Optional[Dict[str, Any]],
) -> tuple[str, str, Dict[str, Any]]:
    """执行 System 2 法条引文核验门禁并标注第一章政策依据来源。"""
    from app.core.guardrails.citation_guardrail import enforce_citation_grounding
    from app.core.rag.citation_ledger import (
        build_policy_registry_citations,
        merge_citation_ledgers,
    )

    retrieved = [r for r in ((audit_metadata or {}).get("retrieved_citations") or []) if isinstance(r, dict)]
    static_records = [r.model_dump(mode="json") for r in build_policy_registry_citations(policy_basis or "")]
    full_ledger = merge_citation_ledgers(retrieved, static_records or None)
    guard_res = enforce_citation_grounding(llm_conclusion, full_ledger, strict=True)

    dynamic_hits = [r for r in full_ledger if r.get("source_type") in {"law_rag", "vector_rag"}]
    parts = [_format_dynamic_policy_tag(r) for r in dynamic_hits]
    if policy_basis:
        parts.append(f"[静态规则兜底] {policy_basis}")
    tagged_policy = "；".join(parts)

    updated_meta = {
        **dict(audit_metadata or {}),
        "verified_citation_count": len(guard_res.verified_ids),
        "blocked_citation_count": len(guard_res.blocked_citations),
        "retrieved_citations": full_ledger,
    }
    return tagged_policy, guard_res.sanitized_text, updated_meta


@dataclass
class RenderedReport:
    """渲染结果容器"""
    markdown: str              # 完整的五章节 Markdown 报告
    summary: str               # 摘要（第四章节的前 200 字）
    risk_level: str            # 高 / 中 / 低
    total_amount: float
    finding_count: int
    audit_metadata: Dict[str, Any] = field(default_factory=dict) # [V156.0] 审计元数据
    sanitized_conclusion: str = ""
    rendered_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AuditReportRenderer:
    """
    确定性五章节审计报告渲染器。

    核心价值：
        用确定性 Python 代码生成报告骨架（4章），
        只有"核查结论"（第4章）需要 LLM 介入，
        从根本上消灭报告截断问题。
    """

    def __init__(
        self,
        risk_thresholds: Optional[Dict] = None,
        max_evidence_rows: int = DEFAULT_MAX_EVIDENCE_ROWS,
        sensitive_fields: Optional[set] = None,
    ):
        self.risk_thresholds = risk_thresholds or DEFAULT_RISK_THRESHOLDS
        self.max_evidence_rows = max_evidence_rows
        self.sensitive_fields = sensitive_fields or SENSITIVE_FIELDS

    # ──────────────────────────────────────────────────────
    # 核心能力：数据预处理与校验 [V150.0]
    # ──────────────────────────────────────────────────────

    def clean_and_parse_raw_data(self, raw_data_str: Any) -> List[Dict[str, Any]]:
        """[Seam 接缝委托] 委托给专职的数据清洗与多轨自愈深模块 RawDataSanitizer"""
        from app.data.raw_data_sanitizer import RawDataSanitizer
        return RawDataSanitizer.sanitize_and_parse(raw_data_str)

    def prepare_conclusion_prompt(
        self,
        user_question: str,
        methodology: str,
        execution_trace: List[str],
        hard_count: int,
        hard_sum: float,
        rewritten_question: Optional[str] = None,
        is_restricted: bool = False,
    ) -> str:
        """[Matt Pocock Deep Module] 构造事实强制对齐且逻辑白盒化之 LLM Prompt，委托给专职深模块"""
        from app.reporting.conclusion_prompt_builder import build_conclusion_prompt
        return build_conclusion_prompt(
            user_question=user_question,
            methodology=methodology,
            execution_trace=execution_trace,
            hard_count=hard_count,
            hard_sum=hard_sum,
            rewritten_question=rewritten_question,
            is_restricted=is_restricted,
        )

    def _extract_boundary_from_raw_data(self, raw_data_str: Any) -> tuple[Optional[int], Optional[str], Optional[str]]:
        """[Matt Pocock Deep Module] 委托给专职的数据清洗与自愈深模块提取时空扫描边界"""
        from app.data.raw_data_sanitizer import RawDataSanitizer
        return RawDataSanitizer.extract_scan_boundary(raw_data_str)


    def render(
        self,
        user_question: str,
        llm_conclusion: str,
        raw_data: Optional[List[Dict[str, Any]]] = None,
        sql_query: Optional[str] = None,
        sql_history: Optional[List[str]] = None, # [V178.9] 全量证据链
        table_info: Optional[str] = None,
        total_amount: float = 0.0,
        finding_count: int = 0,
        policy_basis: Optional[str] = None,
        execution_trace: Optional[List[str]] = None,
        methodology: Optional[str] = None,
        audit_metadata: Optional[Dict[str, Any]] = None, # [V156.0]
        semantic_alignment: Optional[Dict[str, Any]] = None, # [NEW]
        raw_data_str: Optional[str] = None, # [NEW]
        is_restricted: bool = False, # [V2.1]
        format_preference: Optional[str] = None, # [Hermes User Preference Support]
    ) -> RenderedReport:
        """
        生成完整的五章节审计报告。
        """
        raw_data = raw_data or []
        execution_trace = execution_trace or []

        # 动态提取真实 ClickHouse 扫描边界数据 [V215.0]
        total_records, min_time, max_time = self._extract_boundary_from_raw_data(raw_data_str)

        # [V170.0] 隐私保护：对进入报告的所有原始数据执行物理脱敏 [Matt Pocock SSOT]
        from app.core.security.data_masker import mask_audit_data
        raw_data = mask_audit_data(raw_data)

        # ──【企业级 v1.3】合规政策库靶向动态侧载 ──
        detected_policy = match_policies(user_question)
        policy_basis = f"{policy_basis}；{detected_policy}" if policy_basis else detected_policy
        policy_basis += match_oral_policy(user_question)

        # [V88.0] 逻辑修正：即便 raw_data 为空（可能是解析失败），也要优先保留调用方传入的硬性统计值
        if not raw_data:
            total_amount = total_amount if total_amount > 0 else 0.0
            finding_count = finding_count if finding_count > 0 else 0
            if total_amount == 0 and (not llm_conclusion or len(llm_conclusion.strip()) < 10):
                llm_conclusion = "经物理穿透核查，在当前过滤条件下未发现符合特征的异常记录。"
        else:
            actual_total = self._calc_total_amount(raw_data)
            actual_count = len(raw_data)
            total_amount = total_amount if total_amount > 0 else actual_total
            finding_count = finding_count if finding_count > 0 else actual_count

        policy_basis, llm_conclusion, updated_meta = _apply_citation_guardrail(
            policy_basis, llm_conclusion, audit_metadata
        )
        sanitized_conclusion = llm_conclusion

        # [Phase 3] Zero-finding boundary proof + topic-matched visualization + actionable steps
        # — all extracted to policy_matcher.py for testability and separation of concerns
        if finding_count == 0:
            llm_conclusion += build_zero_finding_boundary(
                user_question, total_records, min_time, max_time, table_info, is_restricted=is_restricted
            )
        else:
            # [Phase 3.1] Positive-finding threshold transparency + 3-tier sensitivity
            llm_conclusion += build_positive_finding_boundary(
                user_question=user_question,
                threshold_value=self._extract_threshold_value(sql_query, methodology),
                threshold_type=self._extract_threshold_type(methodology),
                finding_count=finding_count,
                finding_count_plus20=self._estimate_relaxed_count(finding_count, 0.20),
                finding_count_plus50=self._estimate_relaxed_count(finding_count, 0.50),
            )

        llm_conclusion += match_visualization(user_question, finding_count)
        llm_conclusion += build_actionable_steps()

        risk_level = self._calc_risk_level(total_amount, finding_count)

        sections = [
            self._chapter1_task(user_question, policy_basis),
            self._chapter2_scope(sql_query, table_info, execution_trace, methodology, sql_history, semantic_alignment, user_question, is_restricted=is_restricted),
            self._chapter3_findings(raw_data, total_amount, finding_count, is_restricted=is_restricted, format_preference=format_preference),
            self._chapter4_conclusion(llm_conclusion),
            self._chapter5_risk(risk_level, total_amount, finding_count),
            self._chapter6_traceability(updated_meta), # [V156.0]
        ]

        # [V162.2] 获取行政主体名称
        admin_name = self._get_admin_name(updated_meta.get("tenant_id"))
        
        full_markdown = (
            f"# 📋 医保专项稽核报告\n\n"
            f"> **执行主体**：{admin_name}  "
            f"| **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  "
            f"| **数据范围**：{table_info or '结算明细库'}\n\n"
            + "\n\n".join(sections)
        )

        # 摘要：取结论的前 200 字
        summary = llm_conclusion.strip()[:200]
        if len(llm_conclusion.strip()) > 200:
            summary += "..."

        return RenderedReport(
            markdown=full_markdown,
            summary=summary,
            risk_level=risk_level,
            total_amount=total_amount,
            finding_count=finding_count,
            audit_metadata=updated_meta,
            sanitized_conclusion=sanitized_conclusion,
        )

    # ──────────────────────────────────────────────────────
    # 各章节渲染（私有方法）
    # ──────────────────────────────────────────────────────

    def _chapter1_task(self, question: str, policy_basis: Optional[str]) -> str:
        lines = ["## 一、审计任务", "", question, ""]
        if policy_basis:
            lines += [f"**政策依据**：{policy_basis}", ""]
        return "\n".join(lines)

    def _chapter2_scope(
        self,
        sql: Optional[str],
        table_info: Optional[str],
        trace: List[str],
        methodology: Optional[str] = None,
        sql_history: Optional[List[str]] = None,
        semantic_alignment: Optional[Dict[str, Any]] = None,
        user_question: Optional[str] = None,
        is_restricted: bool = False,
    ) -> str:
        """[Matt Pocock Deep Module] 委托给专职的核查口径排版深模块"""
        from app.reporting.scope_section_builder import build_scope_section
        return build_scope_section(
            sql=sql,
            table_info=table_info,
            trace=trace,
            methodology=methodology,
            sql_history=sql_history,
            semantic_alignment=semantic_alignment,
            user_question=user_question,
            is_restricted=is_restricted,
        )

    def _chapter3_findings(
        self,
        raw_data: List[Dict],
        total_amount: float,
        finding_count: int,
        is_restricted: bool = False,
        format_preference: Optional[str] = None,
    ) -> str:
        """[Matt Pocock Deep Module] 委托给专职的数据发现表格排版深模块"""
        from app.reporting.findings_section_builder import build_findings_section
        return build_findings_section(
            raw_data=raw_data,
            total_amount=total_amount,
            finding_count=finding_count,
            is_restricted=is_restricted,
            format_preference=format_preference,
            max_evidence_rows=self.max_evidence_rows,
            sensitive_fields=self.sensitive_fields,
        )

    def _chapter4_conclusion(self, llm_text: str) -> str:
        if not llm_text or not llm_text.strip():
            llm_text = "（本次核查未发现异常，或数据不足以支撑结论判断。）"
        return "\n".join(["## 四、核查结论", "", llm_text.strip(), ""])

    def _chapter5_risk(
        self, risk_level: str, total_amount: float, finding_count: int
    ) -> str:
        """[Matt Pocock Deep Module] 委托给专职的审计风险评估与评级深模块"""
        from app.reporting.traceability_section_builder import build_risk_section
        return build_risk_section(
            risk_level=risk_level,
            total_amount=total_amount,
            finding_count=finding_count,
        )

    def _chapter6_traceability(self, metadata: Dict[str, Any]) -> str:
        """[Matt Pocock Deep Module] 委托给专职的审计溯源存证排版深模块"""
        from app.reporting.traceability_section_builder import build_traceability_section
        return build_traceability_section(metadata)

    # ──────────────────────────────────────────────────────
    # 工具方法（薄包装与兼容委托）
    # ──────────────────────────────────────────────────────

    def _calc_total_amount(self, raw_data: List[Dict]) -> float:
        """从数据中自动计算金额汇总"""
        amount_keys = ["medfee_sumamt", "amount", "total_amount", "fund_pay_sumamt", "amt"]
        total = 0.0
        for row in raw_data:
            for key in amount_keys:
                if key in row:
                    try:
                        total += float(row[key] or 0)
                        break
                    except (ValueError, TypeError):
                        pass
        return total

    def _extract_threshold_value(self, sql_query: Optional[str], methodology: Optional[str]) -> float:
        """从 SQL 或方法论中提取计算阈值"""
        from app.reporting.policy_matcher import extract_threshold_value
        return extract_threshold_value(sql_query, methodology)

    def _extract_threshold_type(self, methodology: Optional[str]) -> str:
        """从方法论描述中提取阈值类型"""
        from app.reporting.policy_matcher import extract_threshold_type
        return extract_threshold_type(methodology)

    def _estimate_relaxed_count(self, original_count: int, relaxation_pct: float) -> int:
        """估算阈值放宽后的发现数量"""
        from app.reporting.policy_matcher import estimate_relaxed_count
        return estimate_relaxed_count(original_count, relaxation_pct)

    def _calc_risk_level(self, total_amount: float, finding_count: int) -> str:
        """根据阈值配置计算风险等级"""
        from app.reporting.traceability_section_builder import calculate_risk_level
        return calculate_risk_level(total_amount, finding_count, self.risk_thresholds)

    def _get_admin_name(self, tenant_id: Optional[str]) -> str:
        """[V162.2] 将租户 ID 转换为行政主体名称"""
        from app.reporting.traceability_section_builder import resolve_admin_name
        return resolve_admin_name(tenant_id)



# Backward-compatible alias, delegates to DI container
from app.core.container import LazyProxy

report_renderer = LazyProxy("report_renderer")
