"""
app/skills/fast_route_matcher.py
================================
快速规则路由匹配引擎（Deep Module）

职责：
- 动态参数提取（尾号、金额等规则过滤槽位）
- 审计意图关键词精确匹配与组合模糊匹配计算
- 任务复杂度启发式评估与模型分级判断 (LIGHT / HEAVY)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Any

from app.skills.fast_router import RouteType, ModelTier, RouteResult


def extract_query_filters(text: str) -> Dict[str, str]:
    """
    从查询文本中提取动态过滤参数（如尾号、金额门限）。
    """
    if not text:
        return {}

    extra_filters: Dict[str, str] = {}
    tail_match = re.search(r"尾号\s*(\d{3,11})", text)
    if tail_match:
        extra_filters["tel"] = f"LIKE '%{tail_match.group(1)}'"

    amt_match = re.search(r"金额\s*[>|超过]\s*(\d+)", text)
    if amt_match:
        extra_filters["medfee_sumamt"] = f"> {amt_match.group(1)}"

    return extra_filters


def estimate_query_complexity(text: str) -> ModelTier:
    """
    复杂度评估器：识别高维分析需求，确定选用轻量模型还是重量模型。
    """
    if not text:
        return ModelTier.LIGHT

    # 简单查询特征词
    light_patterns = ["解释", "定义", "是谁", "查一下", "多少钱"]
    # 复杂分析特征词
    heavy_patterns = ["趋势", "分布", "关联", "对比", "同环比", "异动", "交叉", "特征", "聚集", "偏离"]

    if any(p in text for p in heavy_patterns) or len(text) > 60:
        return ModelTier.HEAVY

    # 如果包含大量“解释”类词汇且长度较短，设为 LIGHT
    if any(p in text for p in light_patterns):
        return ModelTier.LIGHT

    return ModelTier.HEAVY


def match_exact(
    text: str,
    rules: List[Dict[str, Any]],
    extra_filters: Optional[Dict[str, str]] = None,
) -> Optional[RouteResult]:
    """
    精确关键词匹配。
    """
    filters = extra_filters or {}
    for rule in rules:
        for kw in rule.get("exact_keywords", []):
            if kw in text:
                return RouteResult(
                    route_type=rule["route_type"],
                    target_id=rule["target_id"],
                    confidence=1.0,
                    matched_keywords=[kw],
                    extra_filters=filters,
                    reason=f"精确匹配关键词「{kw}」→ {rule.get('description', '')}",
                )
    return None


def match_fuzzy(
    text: str,
    rules: List[Dict[str, Any]],
    extra_filters: Optional[Dict[str, str]] = None,
) -> Optional[RouteResult]:
    """
    模糊关键词组合匹配，找出最高置信度的规则。
    """
    filters = extra_filters or {}
    best: Optional[Tuple[float, RouteResult]] = None

    for rule in rules:
        for group in rule.get("fuzzy_groups", []):
            matched = [kw for kw in group if kw in text]
            if len(matched) == len(group):
                confidence = round(0.7 + 0.05 * (len(group) - 1), 2)
                confidence = min(confidence, 0.95)
                result = RouteResult(
                    route_type=rule["route_type"],
                    target_id=rule["target_id"],
                    confidence=confidence,
                    matched_keywords=matched,
                    extra_filters=filters,
                    reason=f"模糊匹配组合 {matched} → {rule.get('description', '')}",
                )
                if best is None or confidence > best[0]:
                    best = (confidence, result)

    return best[1] if best else None


def match_fast_route(
    user_question: Optional[str],
    rules: List[Dict[str, Any]],
) -> RouteResult:
    """
    快速路由匹配完整管道。
    """
    if not user_question or not user_question.strip():
        return RouteResult(
            route_type=RouteType.UNKNOWN,
            target_id="",
            confidence=0.0,
            reason="问题为空",
        )

    text = user_question.strip()
    extra_filters = extract_query_filters(text)

    # 优先级 1：精确关键词匹配（置信度 1.0）
    result = match_exact(text, rules, extra_filters)
    if result:
        return result

    # 优先级 2：模糊关键词组合匹配（置信度 0.7~0.95）
    result = match_fuzzy(text, rules, extra_filters)
    if result:
        return result

    # 优先级 3：未知类型，根据复杂度进行模型分级
    tier = estimate_query_complexity(text)
    return RouteResult(
        route_type=RouteType.UNKNOWN,
        target_id="",
        confidence=0.0,
        model_tier=tier,
        reason=f"未匹配到任何已知规则，评估复杂度级别为: {tier}",
    )
