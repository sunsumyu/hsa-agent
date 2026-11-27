"""
BFCL 本地 AST 校验器 (对齐官方 possible_answer 语义的轻量实现)。

为什么不用原书的 `ast.dump(pred) == ast.dump(true)`？
1. BFCL v4 的 ground_truth 格式是列表：[{"func_name": {"arg1": [val1, val2], ...}}]，
   每个参数的期望值是「可接受值列表」(例如 `["New York", "NY", "New York, NY"]` 或 `[""]`)，
   不能直接拿来做 Python AST 字符串对比。
2. `ast.dump()` 会保留关键字参数的源码顺序，实际上并不能忽略参数顺序。
3. 官方 `simple_python` / `multiple` / `parallel` / `irrelevance` 分别有各自的语义：
   - irrelevance / live_irrelevance: 预测调用必须为空；
   - parallel / parallel_multiple: 预测调用集合与 ground_truth 集合无序匹配；
   - 可选参数在 ground_truth 中常包含 `""` 或 `None`，缺失时视为匹配。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def _normalize_str(val: str) -> str:
    """对齐 BFCL 字符串标准化：去首尾空白、统一小写并去除部分标点差异。"""
    return val.strip().lower()


def _values_match(pred: Any, expected: Any) -> bool:
    """判断单个参数值是否与某一个候选期望值匹配。"""
    if expected is None:
        return pred is None

    if isinstance(expected, bool):
        return isinstance(pred, bool) and pred == expected

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if isinstance(pred, (int, float)) and not isinstance(pred, bool):
            return math.isclose(float(pred), float(expected), rel_tol=1e-6, abs_tol=1e-6)
        return False

    if isinstance(expected, str):
        if not isinstance(pred, str):
            return False
        return _normalize_str(pred) == _normalize_str(expected)

    if isinstance(expected, list):
        if not isinstance(pred, (list, tuple)) or len(pred) != len(expected):
            return False
        return all(_values_match(p, e) for p, e in zip(pred, expected))

    if isinstance(expected, dict):
        if not isinstance(pred, dict) or set(pred.keys()) != set(expected.keys()):
            return False
        return all(_values_match(pred[k], expected[k]) for k in expected)

    return pred == expected


def _call_matches_gt_item(pred_call: Dict[str, Any], gt_item: Dict[str, Any]) -> Tuple[bool, str]:
    """
    判断一次预测调用 `{name: ..., arguments: ...}` 是否匹配一条 ground_truth
    `{func_name: {param: [acceptable_values...]}}`。
    """
    if len(gt_item) != 1:
        return False, f"非法 ground_truth 结构: {gt_item}"

    gt_name, gt_params = next(iter(gt_item.items()))
    pred_name = pred_call.get("name", "")
    if pred_name != gt_name:
        return False, f"函数名不匹配: 预测 `{pred_name}` != 期望 `{gt_name}`"

    pred_args = pred_call.get("arguments") or {}
    if not isinstance(pred_args, dict):
        return False, f"参数不是 dict: {type(pred_args).__name__}"

    # 1. 检查预测中是否有多余参数（未在 ground_truth 中声明）
    extra_keys = set(pred_args.keys()) - set(gt_params.keys())
    if extra_keys:
        return False, f"存在多余参数: {sorted(extra_keys)}"

    # 2. 检查每一个 ground_truth 参数
    for param, acceptable_values in gt_params.items():
        if not isinstance(acceptable_values, list):
            acceptable_values = [acceptable_values]

        if param not in pred_args:
            # BFCL 用 "" 或 None 在候选列表里表示该参数可选
            if "" in acceptable_values or None in acceptable_values:
                continue
            return False, f"缺少必需参数 `{param}`"

        pred_val = pred_args[param]
        if not any(_values_match(pred_val, cand) for cand in acceptable_values):
            return (
                False,
                f"参数 `{param}` 值不匹配: 预测 {pred_val!r} 不在 {acceptable_values!r} 中",
            )

    return True, "ok"


def check_sample(
    predicted_calls: List[Dict[str, Any]],
    ground_truth: Optional[List[Dict[str, Any]]],
    category: str,
) -> Tuple[bool, str]:
    """
    校验单条 BFCL 样本的预测结果。

    Args:
        predicted_calls: 统一格式 [{"name": str, "arguments": dict}, ...]
        ground_truth:    BFCL possible_answer 中的列表，irrelevance 类为 None/[]
        category:        BFCL 类别名
    Returns:
        (is_correct, reason)
    """
    if category in ("irrelevance", "live_irrelevance"):
        if not predicted_calls:
            return True, "ok (正确未调用工具)"
        return False, f"irrelevance 样本不应调用工具，实际调用: {[c.get('name') for c in predicted_calls]}"

    if not ground_truth:
        return False, "缺少 ground_truth"

    if len(predicted_calls) != len(ground_truth):
        return (
            False,
            f"调用次数不匹配: 预测 {len(predicted_calls)} 次 != 期望 {len(ground_truth)} 次",
        )

    # 无序二分匹配（兼容 parallel / parallel_multiple）
    used = [False] * len(ground_truth)
    last_reason = "未匹配"
    for pred_call in predicted_calls:
        matched = False
        for idx, gt_item in enumerate(ground_truth):
            if used[idx]:
                continue
            ok, reason = _call_matches_gt_item(pred_call, gt_item)
            if ok:
                used[idx] = True
                matched = True
                break
            last_reason = reason
        if not matched:
            return False, last_reason

    return True, "ok"
