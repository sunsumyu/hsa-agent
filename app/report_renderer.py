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
    from app.report_renderer import AuditReportRenderer

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
SENSITIVE_FIELDS = {"psn_name", "certno", "phone", "addr"}


@dataclass
class RenderedReport:
    """渲染结果容器"""
    markdown: str              # 完整的五章节 Markdown 报告
    summary: str               # 摘要（第四章节的前 200 字）
    risk_level: str            # 高 / 中 / 低
    total_amount: float
    finding_count: int
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
    # 公共入口
    # ──────────────────────────────────────────────────────

    def render(
        self,
        user_question: str,
        llm_conclusion: str,
        raw_data: Optional[List[Dict[str, Any]]] = None,
        sql_query: Optional[str] = None,
        table_info: Optional[str] = None,
        total_amount: float = 0.0,
        finding_count: int = 0,
        policy_basis: Optional[str] = None,
        execution_trace: Optional[List[str]] = None,
        methodology: Optional[str] = None,
    ) -> RenderedReport:
        """
        生成完整的五章节审计报告。

        Args:
            user_question:    原始审计问题
            llm_conclusion:   LLM 生成的核查结论文本（第四章节内容）
            raw_data:         SQL 查询返回的原始数据列表
            sql_query:        执行的 SQL 语句
            table_info:       数据表名称描述
            total_amount:     涉及金额汇总
            finding_count:    发现条数
            policy_basis:     适用政策依据
            execution_trace:  执行轨迹日志列表
            methodology:      审计口径/方法论说明文本

        Returns:
            RenderedReport 对象，包含完整 Markdown 和结构化摘要
        """
        raw_data = raw_data or []
        execution_trace = execution_trace or []

        # [V88.0] 逻辑修正：即便 raw_data 为空（可能是解析失败），也要优先保留调用方传入的硬性统计值
        if not raw_data:
            total_amount = total_amount if total_amount > 0 else 0.0
            finding_count = finding_count if finding_count > 0 else 0
            if total_amount == 0:
                llm_conclusion = "经物理穿透核查，在当前过滤条件下未发现符合特征的异常记录。"
        else:
            # 自动从数据中计算金额
            actual_total = self._calc_total_amount(raw_data)
            actual_count = len(raw_data)
            
            # 优先保留调用方传入的硬性统计值 (Hard Metrics)
            total_amount = total_amount if total_amount > 0 else actual_total
            finding_count = finding_count if finding_count > 0 else actual_count

        risk_level = self._calc_risk_level(total_amount, finding_count)

        sections = [
            self._chapter1_task(user_question, policy_basis),
            self._chapter2_scope(sql_query, table_info, execution_trace, methodology),
            self._chapter3_findings(raw_data, total_amount, finding_count),
            self._chapter4_conclusion(llm_conclusion),
            self._chapter5_risk(risk_level, total_amount, finding_count),
        ]

        full_markdown = (
            f"# 📋 医保专项稽核报告\n\n"
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  "
            f"| 数据来源：{table_info or '结算明细库'}\n\n"
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
    ) -> str:
        lines = ["## 二、核查口径与执行过程", ""]
        if table_info:
            lines += [f"- **数据来源**：`{table_info}`"]
        
        if methodology:
            lines += [
                "",
                "**审计方法论**：",
                methodology.strip(),
            ]
            
        if sql:
            lines += [
                "",
                "**执行 SQL**：",
                "```sql",
                sql.strip(),
                "```",
            ]
        if trace:
            lines += ["", "**执行轨迹**："]
            for i, step in enumerate(trace[-5:], 1):  # 最近 5 步
                lines.append(f"{i}. {step}")
        lines.append("")
        return "\n".join(lines)

    def _chapter3_findings(
        self,
        raw_data: List[Dict],
        total_amount: float,
        finding_count: int,
    ) -> str:
        lines = [
            "## 三、核查数据发现",
            "",
            f"**发现条数**：{finding_count} 条 ｜ "
            f"**涉及金额**：¥{total_amount:,.2f}",
            "",
        ]

        if not raw_data:
            lines.append("_在当前核查口径下，未检出符合条件的异常记录。_")
        else:
            rows = raw_data[: self.max_evidence_rows]
            # 动态生成表头（从第一行数据的键推断）
            headers = [k for k in rows[0].keys() if k not in self.sensitive_fields]
            if not headers:
                headers = list(rows[0].keys())

            # Markdown 表格
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in rows:
                cells = []
                for h in headers:
                    val = row.get(h, "")
                    # 对敏感字段脱敏
                    if h in self.sensitive_fields:
                        val = "***"
                    elif isinstance(val, float):
                        val = f"¥{val:,.2f}"
                    cells.append(str(val))
                lines.append("| " + " | ".join(cells) + " |")

            if finding_count > self.max_evidence_rows:
                lines.append(
                    f"\n_（仅展示前 {self.max_evidence_rows} 条，"
                    f"其余 {finding_count - self.max_evidence_rows} 条已固化至证据库）_"
                )
        lines.append("")
        return "\n".join(lines)

    def _chapter4_conclusion(self, llm_text: str) -> str:
        if not llm_text or not llm_text.strip():
            llm_text = "（本次核查未发现异常，或数据不足以支撑结论判断。）"
        return "\n".join(["## 四、核查结论", "", llm_text.strip(), ""])

    def _chapter5_risk(
        self, risk_level: str, total_amount: float, finding_count: int
    ) -> str:
        emoji_map = {"高": "🔴", "中": "🟡", "低": "🟢"}
        emoji = emoji_map.get(risk_level, "⚪")
        return "\n".join([
            "## 五、风险评级",
            "",
            f"| 维度 | 评估结果 |",
            f"| :--- | :--- |",
            f"| 综合风险等级 | {emoji} **{risk_level}风险** |",
            f"| 涉及金额 | ¥{total_amount:,.2f} |",
            f"| 发现条数 | {finding_count} 条 |",
            "",
        ])

    # ──────────────────────────────────────────────────────
    # 工具方法
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

    def _calc_risk_level(self, total_amount: float, finding_count: int) -> str:
        """根据阈值配置计算风险等级"""
        high = self.risk_thresholds.get("high", {})
        medium = self.risk_thresholds.get("medium", {})

        if (total_amount >= high.get("min_amount", float("inf"))
                or finding_count >= high.get("min_count", float("inf"))):
            return "高"
        if (total_amount >= medium.get("min_amount", float("inf"))
                or finding_count >= medium.get("min_count", float("inf"))):
            return "中"
        return "低"


# 模块级单例（供 agent_graph 直接使用）
report_renderer = AuditReportRenderer()
