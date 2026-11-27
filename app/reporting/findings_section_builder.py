"""
app/reporting/findings_section_builder.py
===========================================
[SPEC-227 / Matt Pocock Deep Module] 报告核查数据发现与表格排版深模块 (Findings Section Builder)

核心职责：
1. 审计事实指标透出：统一排版发现条数与涉案总金额；
2. 防御性空态自适应：精准区分“执行受限无数据”与“正常合规无异常记录”；
3. 数据隐私安全脱敏：敏感字段（手机号、证件号、姓名、地址等）统一脱敏为 ***；
4. 自适应多态展示排版：支持标准 Markdown 表格与 LIST 无序列表用户偏好；
5. 证据截断与固化声明：当检出数据超过展示上限时自动截断并添加存证说明。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set


DEFAULT_MAX_EVIDENCE_ROWS = 10
DEFAULT_SENSITIVE_FIELDS: Set[str] = {
    "psn_name", "certno", "phone", "addr", "org_name",
    "fixmedins_name", "id_card", "tel"
}


def build_findings_section(
    raw_data: List[Dict[str, Any]],
    total_amount: float,
    finding_count: int,
    is_restricted: bool = False,
    format_preference: Optional[str] = None,
    max_evidence_rows: int = DEFAULT_MAX_EVIDENCE_ROWS,
    sensitive_fields: Optional[Set[str]] = None,
) -> str:
    """
    构造第三章：核查数据发现。
    """
    sensitive_set = sensitive_fields if sensitive_fields is not None else DEFAULT_SENSITIVE_FIELDS

    lines = [
        "## 三、核查数据发现",
        "",
        f"**发现条数**：{finding_count} 条 ｜ "
        f"**涉及金额**：¥{total_amount:,.2f}",
        "",
    ]

    if is_restricted:
        lines.append("由于 SQL 执行受限，本次未检出任何明细数据。")
    elif not raw_data:
        lines.append("_在当前核查口径下，未检出符合条件的异常记录。_")
    else:
        rows = raw_data[:max_evidence_rows]
        # 动态生成表头（从第一行数据的键推断）
        headers = [k for k in rows[0].keys() if k not in sensitive_set]
        if not headers:
            headers = list(rows[0].keys())

        if format_preference == "LIST":
            # [User Preference] 用户明确偏好无序列表排版
            for idx, row in enumerate(rows, 1):
                item_parts = []
                for h in headers:
                    val = row.get(h, "")
                    if h in sensitive_set:
                        val = "***"
                    elif isinstance(val, float):
                        val = f"¥{val:,.2f}"
                    item_parts.append(f"**{h}**: {val}")
                lines.append(f"- 序号 {idx}：{' ｜ '.join(item_parts)}")
        else:
            # 默认 Markdown 表格
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in rows:
                cells = []
                for h in headers:
                    val = row.get(h, "")
                    if h in sensitive_set:
                        val = "***"
                    elif isinstance(val, float):
                        val = f"¥{val:,.2f}"
                    cells.append(str(val))
                lines.append("| " + " | ".join(cells) + " |")

        if finding_count > max_evidence_rows:
            lines.append(
                f"\n_（仅展示前 {max_evidence_rows} 条，"
                f"其余 {finding_count - max_evidence_rows} 条已固化至证据库）_"
            )

    lines.append("")
    return "\n".join(lines)
