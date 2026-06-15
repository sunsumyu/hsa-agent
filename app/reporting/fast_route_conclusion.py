"""
app/reporting/fast_route_conclusion.py
======================================
[Phase 2] Business conclusion templates for fast-route bypass.

Extracted from agent_graph.reporter_node to separate business text
generation from LangGraph orchestration logic.

When a fast_route_id is set, the system skips LLM conclusion generation
and assembles a deterministic conclusion from raw data using these templates.
"""

from typing import List, Dict, Any
from loguru import logger


_AMOUNT_KEYS = [
    "det_item_fee_sumamt", "total_fee", "fee_b",
    "total_amt", "amount", "medfee_sumamt",
]


def _extract_amount(row: Dict[str, Any]) -> float:
    for key in _AMOUNT_KEYS:
        val = row.get(key)
        if val:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return 0.0


def _extract_psn(row: Dict[str, Any]) -> str:
    return row.get("psn_no") or row.get("PSN_NO") or "未明参保人"


def _extract_hospital(row: Dict[str, Any]) -> str:
    return (
        row.get("hospital")
        or row.get("fixmedins_name")
        or row.get("hospital_a")
        or row.get("fixmedins_code")
        or "未知机构"
    )


def _extract_violation_item(row: Dict[str, Any], hospital: str) -> str:
    item = (
        row.get("hilist_name")
        or row.get("item_name")
        or row.get("tel")
        or "限定性违规结算"
    )
    if row.get("tel"):
        return f"共用联系人电话 {item}"
    if row.get("hospital_b"):
        return f"跨机构住院重叠 ({hospital} 与 {row.get('hospital_b')})"
    return item


def generate_fast_route_conclusion(
    raw_data_list: List[Dict[str, Any]],
    hard_sum: float,
    hard_count: int,
    user_question: str,
) -> str:
    """
    Generate a deterministic audit conclusion for fast-route results.
    No LLM involved — pure template assembly from physical data.
    """
    logger.info(
        f"[Reporter Bypass] Fast route hit, assembling conclusion from "
        f"{hard_count} records, total ¥{hard_sum:,.2f}"
    )

    if hard_count == 0:
        return (
            f"本次核查对底层表进行了全量扫描（扫描基数 > 0，发现违规记录 0 条），"
            f"涉及金额 ¥{hard_sum:,.2f}。经物理穿透核查，在当前过滤条件下"
            f"未发现符合特征的异常记录。"
        )

    sample_details = []
    for row in raw_data_list[:3]:
        psn = _extract_psn(row)
        hospital = _extract_hospital(row)
        item = _extract_violation_item(row, hospital)
        amt = _extract_amount(row)
        sample_details.append(
            f"参保人 {psn} 在 {hospital} 涉及「{item}」违规结算金额 ¥{amt:,.2f}"
        )

    samples_str = "；".join(sample_details)
    return (
        f"根据快速审计路由规则，本次专项核查针对「{user_question}」"
        f"进行了物理穿透扫描。\n\n"
        f"共穿透扫描相关违规明细记录 {hard_count} 条，"
        f"涉及金额 ¥{hard_sum:,.2f}。详细核查发现：\n"
        f"系统检测到存在明确的违规行为。典型违规样本包括：{samples_str}。\n"
        f"这些记录的结算特征、项目限定约束以及临床时序均与审计方法论及"
        f"医保监管政策冲突，判定为明确违规。建议立即启动定向现场审计，"
        f"对相关病案流水及医保支付凭证进行追溯性核查。"
    )
