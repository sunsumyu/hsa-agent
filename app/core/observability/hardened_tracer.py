# app/core/observability/hardened_tracer.py
# -*- coding: utf-8 -*-
"""
[受控探针] 强化型脱敏与采样 Tracer (HardenedTracer)
- 继承 LangChain 官方 LangChainTracer
- 统一集成 AdaptiveSampler：未命中采样的请求在进程内直接丢弃，不产生无效网络调用
- 统一集成 PIISanitizer：所有上报数据离开本地进程前深度脱敏身份证、手机号、银行/社保卡与系统凭证
- 隔离 _send_to_backend 便于单测与网络异常兜底
"""

from typing import Optional, Any
from langchain_core.tracers import LangChainTracer
from app.core.observability.pii_sanitizer import PIISanitizer
from app.core.observability.adaptive_sampler import AdaptiveSampler


class HardenedTracer(LangChainTracer):
    """[受控探针] 统一集成 PII 脱敏与自适应采样的 LangChain 探针"""

    def __init__(self, sampler: Optional[AdaptiveSampler] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sampler = sampler or AdaptiveSampler()

    def _persist_run(self, run: Any) -> None:
        """拦截持久化操作：先采样过滤，后脱敏数据，最后提交后端"""
        # 1. 计算执行耗时
        duration = 0.0
        start_time = getattr(run, "start_time", None)
        end_time = getattr(run, "end_time", None)
        if end_time and start_time:
            duration = (end_time - start_time).total_seconds()

        # 2. 采样决策过滤
        has_error = getattr(run, "error", None) is not None
        tags = getattr(run, "tags", None)
        if not self.sampler.should_sample(has_error=has_error, duration_seconds=duration, tags=tags):
            return

        # 3. 严格 PII 脱敏
        if hasattr(run, "inputs") and run.inputs:
            run.inputs = PIISanitizer.sanitize(run.inputs)
        if hasattr(run, "outputs") and run.outputs:
            run.outputs = PIISanitizer.sanitize(run.outputs)

        # 4. 安全提交给后端
        self._send_to_backend(run)

    def _send_to_backend(self, run: Any) -> None:
        """隔离真实的底层网络提交，便于单元测试与物理故障兜底"""
        super()._persist_run(run)
