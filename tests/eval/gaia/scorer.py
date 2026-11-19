"""
GAIA 准精确匹配 (Quasi Exact Match) 评分器与答案提取。

修正了原书示例的常见缺陷：
1. 先判断数值类型（移除 `$`、`%`、千分位 `,` 后能转为 float），避免 `"1,000"` / `"$1,234.56"`
   因含逗号被误判为列表；
2. 列表答案按 `,` / `;` 分隔并对每个元素做类型感知归一化，同时支持无序比较；
3. 字符串答案转小写、移除冠词 (`a`, `an`, `the`)、压缩多余空白并移除末尾标点。
"""

from __future__ import annotations

import math
import re
from typing import Tuple

_ARTICLES_RE = re.compile(r"\b(?:a|an|the)\b", re.IGNORECASE)
_FINAL_ANSWER_RE = re.compile(r"FINAL\s+ANSWER\s*:\s*(.+?)(?:\r?\n|$)", re.IGNORECASE)
_FALLBACK_PATTERNS = (
    re.compile(r"最终答案\s*[：:]\s*(.+?)(?:\r?\n|$)"),
    re.compile(r"答案\s*[：:]\s*(.+?)(?:\r?\n|$)"),
    re.compile(r"Answer\s*[：:]\s*(.+?)(?:\r?\n|$)", re.IGNORECASE),
)
_CURRENCY_OR_PCT_RE = re.compile(r"[\$€£¥%]")


def extract_final_answer(response: str) -> str:
    """从模型输出中提取 `FINAL ANSWER: ...` 内容。"""
    if not response:
        return ""

    matches = _FINAL_ANSWER_RE.findall(response)
    if matches:
        ans = matches[-1].strip()
        if ans.startswith("[") and ans.endswith("]"):
            ans = ans[1:-1].strip()
        return ans

    for pat in _FALLBACK_PATTERNS:
        m = pat.search(response)
        if m:
            return m.group(1).strip().strip("[]").strip()

    for line in reversed(response.splitlines()):
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            return cleaned
    return response.strip()


def _try_parse_number(text: str) -> Tuple[bool, float]:
    cleaned = _CURRENCY_OR_PCT_RE.sub("", text.strip())
    # 移除千分位逗号 (如 1,234.56 -> 1234.56)
    cleaned = re.sub(r"(?<=\d),(?=\d{3}\b)", "", cleaned)
    cleaned = cleaned.replace(",", "") if re.fullmatch(r"[+-]?[\d,]+(?:\.\d+)?", cleaned) else cleaned
    try:
        val = float(cleaned)
        if math.isfinite(val):
            return True, val
    except ValueError:
        pass
    return False, 0.0


def _normalize_single_str(text: str) -> str:
    s = text.strip().lower()
    s = _CURRENCY_OR_PCT_RE.sub("", s)
    s = _ARTICLES_RE.sub(" ", s)
    s = " ".join(s.split())
    s = s.rstrip(".,;:!?。，；：！？")
    return s.strip()


def normalize_answer(answer: str) -> str:
    """对单个答案做归一化（数值 -> 标准数字串；列表 -> 排序后逗号拼接；文本 -> 规范字符串）。"""
    if not answer:
        return ""
    raw = answer.strip()

    is_num, num_val = _try_parse_number(raw)
    if is_num:
        return str(int(num_val)) if num_val.is_integer() else f"{num_val:g}"

    if "," in raw or ";" in raw:
        sep = ";" if ";" in raw and "," not in raw else ","
        parts = []
        for part in raw.split(sep):
            p = part.strip()
            p_is_num, p_num = _try_parse_number(p)
            if p_is_num:
                parts.append(str(int(p_num)) if p_num.is_integer() else f"{p_num:g}")
            else:
                parts.append(_normalize_single_str(p))
        parts.sort()
        return ",".join(parts)

    return _normalize_single_str(raw)


def quasi_exact_match(predicted: str, ground_truth: str) -> Tuple[bool, str]:
    """
    GAIA 准精确匹配。
    Returns:
        (is_match, reason)
    """
    gt_raw = (ground_truth or "").strip()
    pred_raw = (predicted or "").strip()

    if not gt_raw:
        return False, "缺少 ground_truth"

    # 1. 若标准答案是数值，按数值比较
    gt_is_num, gt_num = _try_parse_number(gt_raw)
    if gt_is_num:
        pred_is_num, pred_num = _try_parse_number(pred_raw)
        if pred_is_num and math.isclose(pred_num, gt_num, rel_tol=1e-6, abs_tol=1e-6):
            return True, "ok (numeric)"
        return False, f"数值不匹配: 预测 {pred_raw!r} != 期望 {gt_raw!r}"

    # 2. 归一化字符串/列表比较
    norm_pred = normalize_answer(pred_raw)
    norm_gt = normalize_answer(gt_raw)
    if norm_pred == norm_gt:
        return True, "ok"
    return False, f"不匹配: 归一化 `{norm_pred}` != `{norm_gt}`"
