# -*- coding: utf-8 -*-
"""
app/core/observability_service.py
==================================
[Matt Pocock Deep Module] 统一企业级可观测服务 (ObservabilityService)
对外呈现极其克制的 5 个核心接口，对内吞噬所有异构探针、采样与合规脱敏细节。

遵循 Matt Pocock Deep Module 核心设计准则：
- Small Interface: 仅暴露 configure_run, get_stream_callbacks, record_feedback, shutdown, node_scope
- Deep Implementation: 内部处理 PII 脱敏、智能采样、网络探活、双向环境变量同步与优雅 Flush
- Information Hiding: 绝对不向外部泄漏第三方 SDK client 原生类型
"""

import os
import sys
import time
import socket
import random
import re
from contextlib import contextmanager
from typing import Dict, Any, List, Optional
from loguru import logger
from langchain_core.runnables import RunnableConfig

from app.core.observability.pii_sanitizer import PIISanitizer
from app.core.observability.adaptive_sampler import AdaptiveSampler
from app.core.observability.hardened_tracer import HardenedTracer
from app.core.observability.session_manager import SessionContextManager
from app.core.observability.feedback_collector import FeedbackCollector


def sanitize_pii_payload(val: Any) -> Any:
    """递归脱敏敏感字段，防止明文上报到公网 (委托至 PIISanitizer)"""
    return PIISanitizer.sanitize(val)


class ObservabilityService:
    """[Matt Pocock Deep Module] 受控可观测深模块服务实现"""

    def __init__(self, sample_rate: float = 0.05, slow_threshold: float = 8.0):
        self.sample_rate = sample_rate
        self.slow_threshold = slow_threshold

        self.sampler = AdaptiveSampler(sample_rate=sample_rate, slow_threshold=slow_threshold)
        self.feedback_collector: Optional[FeedbackCollector] = None

        self._langsmith_client = None
        self._langsmith_tracer = None
        self._langfuse_handler = None
        self._tracer_provider = None
        self._phoenix_session = None

        self._init_environment()
        self._init_otel_phoenix()
        self._init_langfuse()
        self._init_langsmith()

    # ── 内部初始化与深实现 ─────────────────────────────────────

    def _init_environment(self):
        os.environ["PYTHONIOENCODING"] = "utf-8"
        os.environ["PYTHONUTF8"] = "1"

    def _is_network_reachable(self, host_or_url: str, port: int = 443, timeout: float = 1.5) -> bool:
        """网络探活：代理环境下直接放行，直连环境下做 Socket 连通性预检"""
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("ALL_PROXY") or os.getenv("all_proxy")
        if proxy:
            return True
        clean_host = host_or_url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        try:
            with socket.create_connection((clean_host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def _sanitize_pii(self, val: Any) -> Any:
        """内部与契约测试使用的脱敏方法"""
        return sanitize_pii_payload(val)

    def _init_otel_phoenix(self):
        if os.getenv("DISABLE_PHOENIX", "false").lower() == "true":
            return
        try:
            import phoenix as px
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource, SERVICE_NAME
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from openinference.instrumentation.langchain import LangChainInstrumentor

            os.environ["PHOENIX_GRPC_PORT"] = "4517"
            os.environ["PHOENIX_HOST"] = "127.0.0.1"
            self._phoenix_session = px.launch_app()

            if self._is_network_reachable("127.0.0.1", port=4517, timeout=0.5):
                provider = TracerProvider(resource=Resource({SERVICE_NAME: "argus-agent"}))
                exporter = OTLPSpanExporter(endpoint="http://127.0.0.1:4517", insecure=True)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                self._tracer_provider = provider
                trace.set_tracer_provider(provider)
                LangChainInstrumentor().instrument(tracer_provider=provider)
                logger.info(">>> [Observability] Phoenix OTel 链路已就绪")
        except Exception as e:
            logger.debug(f">>> [Observability] Phoenix 离线旁路: {e}")

    def _init_langfuse(self):
        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if pk and sk and self._is_network_reachable(host):
            try:
                from langfuse.langchain import CallbackHandler
                self._langfuse_handler = CallbackHandler(public_key=pk)
                logger.info(">>> [Observability] Langfuse 链路已激活")
            except Exception as e:
                logger.warning(f"⚠️ [Observability] Langfuse 初始化异常: {e}")

    def _init_langsmith(self):
        api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
        tracing = (os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2", "")).lower()
        if not api_key or tracing in ("false", "0"):
            return

        endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        project = os.getenv("LANGSMITH_PROJECT", "argus-agent")

        # 双向环境变量对齐
        os.environ["LANGSMITH_API_KEY"] = api_key
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_PROJECT"] = project
        os.environ["LANGSMITH_ENDPOINT"] = endpoint

        if not self.sampler.is_network_reachable(endpoint):
            logger.warning("⚠️ [Observability] LangSmith 终端不可达，已自动旁路")
            return

        try:
            from langsmith import Client

            self._langsmith_client = Client(api_key=api_key, api_url=endpoint)
            self._langsmith_tracer = HardenedTracer(
                project_name=project,
                client=self._langsmith_client,
                sampler=self.sampler
            )
            self.feedback_collector = FeedbackCollector(client=self._langsmith_client)
            logger.success(f"🎉 [Observability] LangSmith 原生链路就绪 (脱敏 + 采样激活)")
        except Exception as e:
            logger.warning(f"⚠️ [Observability] LangSmith 初始化失败: {e}")

    # ── 对外接缝接口 (Matt Pocock Minimal Interface) ──────────

    def get_stream_callbacks(self) -> List[Any]:
        """为顶层 Graph 流式执行器输出回调句柄集合"""
        callbacks = []
        if self._langfuse_handler:
            callbacks.append(self._langfuse_handler)
        if self._langsmith_tracer:
            callbacks.append(self._langsmith_tracer)
        return callbacks

    def configure_run(
        self,
        node_name: str,
        session_id: str,
        extra_meta: Optional[Dict[str, Any]] = None,
        base_config: Optional[RunnableConfig] = None
    ) -> RunnableConfig:
        """
        [接缝收口] 统一为节点调用生成挂载好回调与通用元数据的配置字典。
        """
        cfg = base_config.copy() if base_config else {}
        callbacks = self.get_stream_callbacks()

        if "callbacks" not in cfg or cfg["callbacks"] is None:
            cfg["callbacks"] = callbacks
        elif isinstance(cfg["callbacks"], list):
            cfg["callbacks"].extend(callbacks)

        if "metadata" not in cfg:
            cfg["metadata"] = {}

        cfg["metadata"].update({
            "node": node_name,
            "session_id": session_id,
            "user_id": session_id,
            **(extra_meta or {})
        })
        return cfg

    def record_feedback(
        self,
        run_id: str,
        score: float,
        category: Optional[str] = None,
        comment: Optional[str] = None
    ) -> bool:
        """
        [封装隔离] 记录人工反馈。彻底向外部调用方隐藏具体的 LangSmith Client 对象。
        """
        if self.feedback_collector:
            return self.feedback_collector.record_auditor_feedback(
                run_id=run_id,
                is_accepted=(score >= 0.5),
                feedback_category=category,
                comment=comment
            )
        elif self._langsmith_client:
            try:
                self._langsmith_client.create_feedback(
                    run_id=run_id,
                    key="user_score",
                    score=score,
                    value=category,
                    comment=comment
                )
                return True
            except Exception as e:
                logger.error(f"[Observability] Feedback 记录失败: {e}")
                return False
        logger.debug("[Observability] LangSmith 未激活，忽略 Feedback 上报")
        return False

    @contextmanager
    def node_scope(self, node_name: str, session_id: str, state: Dict[str, Any]):
        """
        [Matt Pocock 作用域深封装] 节点执行上下文管理器
        """
        start_t = time.time()
        retry_count = state.get("retry_count", 0)

        # 尝试派发本地管线追踪
        try:
            from app.core.pipeline_tracker import pipeline_tracker
            pipeline_tracker.on_node_start(node_name, state)
        except Exception:
            pass

        scope_meta = {
            "langgraph_node": node_name,
            "session_id": session_id,
            "retry_count": retry_count,
            "phase": "audit_execution"
        }
        logger.debug(f">>> [Scope Start] {node_name} (Round {retry_count})")

        try:
            yield scope_meta
            duration_ms = (time.time() - start_t) * 1000
            logger.debug(f"<<< [Scope Done] {node_name} ({duration_ms:.1f}ms)")
        except Exception as e:
            logger.error(f"❌ [Scope Error] 节点 {node_name} 异常: {e}")
            raise e

    def shutdown(self) -> None:
        """安全离场，强制刷新缓存数据入盘"""
        if self._tracer_provider:
            try:
                self._tracer_provider.force_flush(2000)
                self._tracer_provider.shutdown()
            except Exception:
                pass
        if self._phoenix_session:
            try:
                import phoenix as px
                px.close_app()
            except Exception:
                pass
        logger.info(">>> [Observability] 可观测服务已优雅安全下线")
