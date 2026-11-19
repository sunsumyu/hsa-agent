"""
app/memory/decay_scoring.py
===========================
[Matt Pocock Deep Module] 记忆时间衰减与相关度评分计算纯函数

确定性数学模型：
1. 距离向相似度映射：similarity = 1.0 / (1.0 + raw_l2_score)
2. 时间衰减因子：time_weight = exp(-decay_rate * days_passed)
   - 当天事件（days_passed = 0）：time_weight = 1.0
   - 缺少时间戳元数据时采用默认降权因子：time_weight = 0.8
3. 综合相关度得分：final_score = similarity * time_weight
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional, Union


def compute_decayed_score(
    raw_l2_score: float,
    timestamp: Optional[Union[str, datetime]] = None,
    decay_rate: float = 0.05,
    now: Optional[datetime] = None,
) -> float:
    """
    计算融合 L2 几何距离与时间衰减的最终记忆相关度评分。

    :param raw_l2_score: 向量索引返回的 L2 欧式距离（非负）
    :param timestamp: 记忆项沉淀的时间戳（ISO 字符串或 datetime）
    :param decay_rate: 指数衰减率，默认 0.05（每日衰减约 5%）
    :param now: 当前比对基准时间，默认为 datetime.now()
    :return: 最终综合评分（归一化近似区间 [0.0, 1.0]）
    """
    current_time = now or datetime.now()

    # 1. 将 L2 距离转换为近似相似度区间 (0, 1]
    safe_l2 = max(0.0, float(raw_l2_score))
    similarity = 1.0 / (1.0 + safe_l2)

    # 2. 计算基于时间跨度的指数衰减
    if timestamp is not None:
        if isinstance(timestamp, str):
            try:
                ts_dt = datetime.fromisoformat(timestamp)
            except Exception:
                ts_dt = None
        elif isinstance(timestamp, datetime):
            ts_dt = timestamp
        else:
            ts_dt = None

        if ts_dt is not None:
            days_passed = max(0, (current_time - ts_dt).days)
            time_weight = math.exp(-decay_rate * days_passed)
        else:
            time_weight = 0.8
    else:
        time_weight = 0.8  # 无时间戳降权

    return similarity * time_weight
