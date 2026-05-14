"""
[V14.0] 企业级受控观测系统 (Hardened Observability Stack)
采用显式 Provider 配置与异步批处理处理器，实现观测逻辑与数据链路的物理隔离。
"""
import os
import sys
import time
import atexit
from loguru import logger
from typing import List, Any
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

# OpenTelemetry 核心组件
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.langchain import LangChainInstrumentor
from langchain_core.runnables import RunnableConfig

# 全局观测句柄容器 (V40.0 增强)
_langfuse_handler = None
_langfuse_client = None
_phoenix_session = None
_tracer_provider = None

def shutdown_observability():
    """优雅停止观测系统，确保 Trace 数据刷盘并关闭 gRPC 服务"""
    global _tracer_provider, _phoenix_session
    
    if not _tracer_provider and not _phoenix_session:
        return

    try:
        if not sys.stderr.closed:
            sys.stderr = open(os.devnull, 'w')
    except (AttributeError, ValueError):
        pass
    
    try:
        import phoenix as px
        if _tracer_provider:
            print(">>> [Observability] 正在执行离场数据固化 (V14.6)...")
            try:
                _tracer_provider.force_flush(2000)
            except Exception: pass
            _tracer_provider.shutdown()
            _tracer_provider = None
        
        if _phoenix_session:
            # [V40.1] 显式关闭 Phoenix 本地应用
            px.close_app()
            _phoenix_session = None
            
        print(">>> [Observability] 审计观测链路已安全切断。")
    except (Exception, KeyboardInterrupt, GeneratorExit, asyncio.CancelledError):
        pass

def init_observability():
    """初始化加固型观测系统 (支持 OTel 与 Langfuse 二位一体)"""
    global _langfuse_handler, _langfuse_client, _phoenix_session, _tracer_provider
    
    # 0. 环境编码加固
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"
    
    # 1. OpenTelemetry & Phoenix 物理初始化
    try:
        os.environ["PHOENIX_GRPC_PORT"] = "4517"
        os.environ["PHOENIX_HOST"] = "127.0.0.1"
        phoenix_dir = os.path.join(os.getcwd(), "data", "phoenix")
        os.makedirs(phoenix_dir, exist_ok=True)
        os.environ["PHOENIX_DATA_DIR"] = phoenix_dir

        import phoenix as px
        import io
        from contextlib import redirect_stdout, redirect_stderr
        
        with io.StringIO() as buf, redirect_stdout(buf), redirect_stderr(buf):
            _phoenix_session = px.launch_app()
        
        resource = Resource(attributes={
            SERVICE_NAME: "hsa-audit-agent",
            "version": "40.1-cloud-managed",
            "environment": "production-hardened"
        })
        
        provider = TracerProvider(resource=resource)
        
        # [V131.5] 增加物理探测：若端口未开放，则不加载 Exporter，防止后台重试报错干扰用户
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            is_collector_up = (s.connect_ex(("127.0.0.1", 4517)) == 0)

        if is_collector_up:
            exporter = OTLPSpanExporter(endpoint="http://127.0.0.1:4517", insecure=True)
            processor = BatchSpanProcessor(exporter, max_queue_size=1024, max_export_batch_size=256, schedule_delay_millis=5000)
            provider.add_span_processor(processor)
            logger.info(">>> [Observability] OTel 导出器已挂载至 127.0.0.1:4517")
        else:
            logger.debug(">>> [Observability] Phoenix 采集器未就绪，Trace 导出已自动旁路（防止报错干扰）")
        
        _tracer_provider = provider
        trace.set_tracer_provider(provider)
        
        LangChainInstrumentor().instrument(
            tracer_provider=provider,
            excluded_urls="172.25.128.80,127.0.0.1:4517,127.0.0.1:6006"
        )
        
        logger.info(">>> [Observability] OTel 异步加固插桩已就绪")
        
    except Exception as e:
        logger.error(f"[Observability] OTel 初始化异常: {e}")

    # 2. Langfuse 物理初始化 (V131.6 加固型：增加云端连通性预检)
    try:
        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        
        if pk and sk:
            # [V131.6] 连通性预检：避免在国内网络环境下因 cloud.langfuse.com 超时导致的系统卡顿
            import socket
            is_langfuse_reachable = False
            try:
                # 提取 host (处理 https:// 前缀)
                clean_host = host.replace("https://", "").replace("http://", "").split(":")[0]
                with socket.create_connection((clean_host, 443), timeout=1.5):
                    is_langfuse_reachable = True
            except:
                pass

            if is_langfuse_reachable:
                # 初始化 Client 用于 Prompt Management
                _langfuse_client = Langfuse(public_key=pk, secret_key=sk, host=host)
                # 初始化 Handler 用于 Trace 追踪
                from langfuse.langchain import CallbackHandler
                _langfuse_handler = CallbackHandler(public_key=pk)
                logger.info(f">>> [Observability] Langfuse 云端链路已激活 ({clean_host})")
            else:
                logger.warning(">>> [Observability] Langfuse 云端不可达，已自动切换至本地脱机模式")
    except Exception as e:
        logger.warning(f"[Observability] Langfuse 物理初始化失败: {e}")

def get_callbacks(tags: List[str] = None) -> List:
    """[V37.5] 获取集成回调列表"""
    return [_langfuse_handler] if _langfuse_handler else []

def get_langfuse_prompt(prompt_name: str, fallback: Any) -> Any:
    """[V40.0] 云端 Prompt 托管助手：优先从云端拉取，物理失败则回退本地"""
    if not _langfuse_client:
        return fallback
    
    try:
        # 开启 60 秒本地缓存，防止高频请求及网络抖动
        prompt = _langfuse_client.get_prompt(prompt_name, cache_ttl_seconds=60)
        # 将 Langfuse 格式物理转化为 LangChain 格式
        from langchain_core.prompts import ChatPromptTemplate
        return ChatPromptTemplate.from_messages([
            ("system", prompt.prompt),
            # 物理兼容：这里可以根据需要注入消息占位符
        ])
    except Exception as e:
        logger.warning(f"[Prompts] 无法从云端获取 {prompt_name}，物理回退至本地: {e}")
        return fallback

def build_obs_config(config: RunnableConfig, node_name: str, state: dict) -> RunnableConfig:
    """[V37.5] 推理链路插桩助手"""
    new_config = config.copy() if config else {}
    callbacks = get_callbacks()
    
    if "callbacks" not in new_config or new_config["callbacks"] is None:
        new_config["callbacks"] = callbacks
    elif isinstance(new_config["callbacks"], list):
        new_config["callbacks"].extend(callbacks)
    
    if "metadata" not in new_config:
        new_config["metadata"] = {}
        
    s_id = state.get("session_id", "unknown")
    feedback = state.get("audit_feedback")
    
    new_config["metadata"].update({
        "node": node_name,
        "user_id": s_id,
        "session_id": s_id,
        "retry_count": state.get("retry_count", 0),
        "audit_decision": getattr(feedback, "decision", "N/A") if feedback else "N/A"
    })
    
    return new_config
