"""
app/infra/usage_window_tracker.py
=================================
[V4.9.6] 分钟级滑动窗口与模型性能画像追踪深模块
负责毫秒级耗时移动平均、分钟级调用频次 (RPM) 与吞吐量 (TPM) 聚合计算与内存清理。
"""

from typing import Dict, List


class UsageWindowTracker:
    """管理模型分钟级流量窗口与延迟统计"""

    def __init__(self, max_latency_samples: int = 10):
        # {model_id: {minute: count}}
        self.rpm_window: Dict[str, Dict[str, int]] = {}
        # {model_id: {minute: tokens}}
        self.tpm_window: Dict[str, Dict[str, int]] = {}
        # {model_id: [ms, ms, ...]}
        self.latency_window: Dict[str, List[float]] = {}
        self.max_latency_samples = max_latency_samples

    def record(self, model_id: str, minute: str, tokens: int = 0, latency_ms: float = 0.0) -> None:
        """记录单次模型调用指标"""
        # 更新 RPM
        if model_id not in self.rpm_window:
            self.rpm_window[model_id] = {}
        self.rpm_window[model_id][minute] = self.rpm_window[model_id].get(minute, 0) + 1

        # 更新 TPM
        if tokens > 0:
            if model_id not in self.tpm_window:
                self.tpm_window[model_id] = {}
            self.tpm_window[model_id][minute] = self.tpm_window[model_id].get(minute, 0) + tokens

        # 更新耗时画像
        if latency_ms > 0:
            if model_id not in self.latency_window:
                self.latency_window[model_id] = []
            self.latency_window[model_id].append(latency_ms)
            if len(self.latency_window[model_id]) > self.max_latency_samples:
                self.latency_window[model_id].pop(0)

    def get_rpm(self, model_id: str, minute: str) -> int:
        """获取指定模型在特定分钟的请求次数"""
        return self.rpm_window.get(model_id, {}).get(minute, 0)

    def get_tpm(self, model_id: str, minute: str) -> int:
        """获取指定模型在特定分钟的 Token 吞吐量"""
        return self.tpm_window.get(model_id, {}).get(minute, 0)

    def get_avg_latency(self, model_id: str) -> float:
        """获取指定模型的平均耗时 (ms)"""
        window = self.latency_window.get(model_id, [])
        if not window:
            return 0.0
        return sum(window) / len(window)

    def prune(self, current_minute: str) -> None:
        """清理过期分钟的滑动窗口数据（仅保留当前活跃分钟）"""
        for window in [self.rpm_window, self.tpm_window]:
            for model_id in list(window.keys()):
                minutes = list(window[model_id].keys())
                for m in minutes:
                    if m != current_minute:
                        del window[model_id][m]
