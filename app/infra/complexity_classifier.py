"""
Complexity Classifier Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates domain heuristic
signals, text length thresholds, and complexity tier evaluation behind a simple API.
"""
from typing import Optional


class ComplexityClassifier:
    """启发式复杂度分类器深模块"""

    _COMPLEX_SIGNALS = (
        "团伙", "欺诈环", "共用", "联邦", "图谱", "多层关联",
        "跨机构", "跨年", "环路", "图分析", "graph", "fraud_ring",
    )
    _SIMPLE_SIGNALS = (
        "性别冲突", "重复收费", "查一下", "列出", "显示",
        "总数", "数量", "多少",
    )

    @classmethod
    def classify(cls, text: Optional[str]) -> str:
        """
        启发式复杂度分类：
          - HIGH: 命中复杂信号 (团伙/联邦/图谱) 或 文本超过 200 字符
          - LOW: 命中简单信号 (性别冲突/查一下) 且 文本简短 (<50字符)
          - MEDIUM: 默认中等复杂度
        """
        if not text:
            return "MEDIUM"

        t = text.lower()
        if any(s in text for s in cls._COMPLEX_SIGNALS) or any(s in t for s in ("fraud_ring", "graph", "联邦")):
            return "HIGH"
        if len(text) > 200:
            return "HIGH"
        if any(s in text for s in cls._SIMPLE_SIGNALS) and len(text) < 50:
            return "LOW"
        return "MEDIUM"
