# app/core/observability/adaptive_sampler.py
# -*- coding: utf-8 -*-
"""
[成本控制与可用性保障] 自适应采样与网络熔断器 (AdaptiveSampler)
- 错误、慢请求、人工协同/门禁请求 100% 采样
- 正常流量按既定比率采样
- 基于 Socket 级探测提供网络可达性与熔断感知
"""
import os
import socket
import random
from typing import List, Optional


class AdaptiveSampler:
    """[成本控制与可用性保障] 自适应采样与网络熔断器"""

    def __init__(self, sample_rate: float = 0.05, slow_threshold: float = 8.0):
        self.sample_rate = sample_rate
        self.slow_threshold = slow_threshold

    def is_network_reachable(self, host_or_url: str, port: int = 443, timeout: float = 1.0) -> bool:
        """
        轻量级探测后端链路是否可达（如 LangSmith API 端点）。
        若存在代理环境配置则直接视为可达，避免代理环境下的直连探测伪失败。
        """
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("ALL_PROXY")
        if proxy:
            return True
        clean_host = (
            host_or_url.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .split(":")[0]
        )
        try:
            with socket.create_connection((clean_host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def should_sample(
        self,
        has_error: bool,
        duration_seconds: float,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        根据执行状态判定是否上报追踪记录：
        1. 发生异常 100% 采样
        2. 慢调用 (耗时 >= slow_threshold) 100% 采样
        3. 带有 HITL (人工介入) 或 Gate (门禁) 标签 100% 采样
        4. 普通流量按 sample_rate 概率采样
        """
        # 1. 异常 100% 采样
        if has_error:
            return True
        # 2. 慢查询 100% 采样
        if duration_seconds >= self.slow_threshold:
            return True
        # 3. 人工协同 / 审计门禁 100% 采样
        current_tags = tags or []
        if any("hitl" in t.lower() or "gate" in t.lower() for t in current_tags):
            return True
        # 4. 正常流量按既定比率采样
        return random.random() < self.sample_rate
