"""
app/core/tool_engine/evidence_truncation_policy.py
=========================================
[Matt Pocock Deep Module] 审计证据截断与宏观保全策略深模块

核心职责：
1. 截断超长大结果集，防止 LLM 上下文超限。
2. 对结构化数据集进行截断时，保全 JSON 语法完整性并注入首行宏观统计 (total_records, total_amount, is_truncated)。
3. 确保下游 AuditMetricEvaluator 等模块能够从首行元数据中对账还原全盘检出数量与总金额。
"""

from __future__ import annotations
import json
from typing import Any
from loguru import logger


def truncate_evidence_data(data: Any, max_chars: int = 12000) -> str:
    """截断超长数据集防止上下文溢出，结构化数据保持 JSON 语法完整并保全宏观汇总"""
    if isinstance(data, list):
        total_items = len(data)
        sampled = []
        current_chars = 2  # '[' and ']'
        for item in data:
            item_str = json.dumps(item, ensure_ascii=False, default=str)
            if current_chars + len(item_str) > max_chars and sampled:
                break
            sampled.append(item)
            current_chars += len(item_str) + 2
        
        if len(sampled) < total_items:
            logger.warning(f"🚨 [State Safeguard] 结果集过大 ({total_items} 条)，结构化保留前 {len(sampled)} 条记录并保全宏观汇总。")
            total_amt = 0.0
            for item in data:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if any(ak in k.lower() for ak in ["amt", "fee", "price", "sum", "金额"]):
                            try:
                                total_amt += float(v or 0)
                                break
                            except (ValueError, TypeError) as exc:
                                logger.debug(f"[EvidenceTruncation] numeric amount skipped: {exc}")
            meta_row = {
                "total_records": total_items,
                "total_amount": round(total_amt, 2) if total_amt > 0 else None,
                "is_truncated": True
            }
            sampled.insert(0, meta_row)
        return json.dumps(sampled, ensure_ascii=False, default=str)
    elif isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False, default=str)

    data_str = str(data)
    if len(data_str) > max_chars:
        logger.warning(f"🚨 [State Safeguard] 结果集过大 ({len(data_str)} chars)，自动截断至 {max_chars} chars。")
        return (
            data_str[:max_chars]
            + f"... \n\n[WARNING: Data truncated due to excessive length. Original length: {len(data_str)} chars]"
        )
    return data_str
