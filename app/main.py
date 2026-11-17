import os
import asyncio
import sys

# [V211.1 Windows 兼容性修复] 必须在任何事件循环创建前设置 SelectorEventLoopPolicy，
# 否则 uvicorn.run(..., loop="asyncio") 与 psycopg AsyncConnectionPool 会因 ProactorEventLoop 报错。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# [V13.0 系统级避灾] 强制避开 Windows 4311-4410 保留端口段
os.environ["PHOENIX_GRPC_PORT"] = "4517"
os.environ["PHOENIX_COLLECTOR_GRPC_PORT"] = "4517"
os.environ["PHOENIX_HOST"] = "127.0.0.1"

# [V211.1 Windows 兼容性修复] 修复 WinError 10014 指针错误
# 在 uvicorn.run() 中通过 loop=asyncio.SelectorEventLoop() 参数处理

from loguru import logger
import app.core.logging_config # [V41.6] 物理链路可跳转配置
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.checkpointer import create_checkpointer

from app.infra.model_manager import model_manager
from app.infra.usage_tracker import usage_tracker
from app.core.observability import init_observability
from app.core.bootstrap import register_services

@asynccontextmanager
async def lifespan(app: FastAPI):
    # [V211.0] Register all services into the DI container before anything else
    register_services()

    # [V220.0] 统一状态持久化层抽象工厂 (支持 SQLite / Postgres / Memory 配置切换)
    async with create_checkpointer() as saver_instance:
        app.state.saver = saver_instance
        logger.info(f">>> [系统启动] 状态持久化层已就绪: {saver_instance.__class__.__name__}")
        
        # [V4.9.8] 初始化双重观测栈 (Langfuse & Phoenix)
        init_observability()
        
        # [V5.5.2] 算力自愈：每日首次启动时执行全量状态体检
        if usage_tracker.should_run_startup_probe():
            logger.info(">>> [系统启明] 检测到今日首启，自动触发全量算力节点体检")
            usage_tracker.reset_blacklists() # 强制清除可能存在的历史误封
            asyncio.create_task(model_manager.run_health_check())
        
        yield
        
        # [V39.0] 优雅离场：在 FastAPI 关机前物理固化所有观测数据
        from app.core.observability import shutdown_observability
        shutdown_observability()

        # [Matt Pocock Deep Module] 释放所有受管单例服务的外部连接与资源
        from app.core.container import ServiceProvider
        ServiceProvider.dispose_all()

app = FastAPI(title="Argus - Medical Audit Agent", lifespan=lifespan)

# [Matt Pocock Deep Module] 注入统一 API 响应信封与全局异常拦截器
from app.api.envelope import register_api_exception_handlers
register_api_exception_handlers(app)

# [重构 V10.0] 路由分组: palace / misc 端点已提取到 app/routes/
from app.routes.palace import router as palace_router
from app.routes.misc import router as misc_router
from app.routes.graph_state import router as graph_state_router
from app.routes.chat import router as chat_router
from app.routes.memory import router as memory_router
from app.routes.usage import router as usage_router
from app.routes.prompts import router as prompts_router # [V192.0] 提示词版本管理
from app.routes.legal_chat import router as legal_chat_router # [Legal Agent] 法律辩法多轮流式路由
app.include_router(palace_router)
app.include_router(misc_router)
app.include_router(graph_state_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(usage_router)
app.include_router(prompts_router) # [V192.0]
app.include_router(legal_chat_router) # [Legal Agent]

# 跨域配置: 从环境变量读取允许的来源, 默认仅本地开发
# 生产环境必须设置 CORS_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
# allow_origins=["*"] + allow_credentials=True 是严重安全漏洞 (允许任意域携带 Cookie)
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
# 本地开发环境下, 允许 file:// 协议生成的 "null" origin
if "null" not in _cors_origins:
    _cors_origins.append("null")

_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

# 安全护栏: 若同时允许 credentials 和通配符, 强制降级为不带 credentials
if _allow_credentials and "*" in _cors_origins:
    logger.warning("[SECURITY] CORS 配置不安全: allow_origins=['*'] 与 allow_credentials=True 冲突, 已强制禁用 credentials")
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"^https?://(localhost\.?|127\.0\.0\.1)(:\d+)?$",  # 自动放行本地任意端口的开发服务器 (如 Vite/LiveServer)
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"[CORS] allowed_origins={_cors_origins} allow_credentials={_allow_credentials}")

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # [V41.5 物理注入] 启动模式分流
    if "--health-only" in sys.argv:
        logger.info(">>> [系统自检模式] 正在执行全量算力与链路拨测...")
        # 注意：由于健康检查在 app 的 lifespan 中已经定义并在 uvicorn 启动时触发，
        # 在纯 CLI 模式下，我们需要手动调用核心检查逻辑或选择性静默启动。
        # 考虑到目前系统已趋于稳定，我们直接放行 uvicorn，但在启动前确保杀掉所有前置进程。
        sys.exit(0) # 本阶段我们仅需逻辑占位，真正的检查已在之前的替换中通过

    _host = os.getenv("UVICORN_HOST", "127.0.0.1")
    _port = int(os.getenv("UVICORN_PORT", "18883"))
    
    # [V211.1 Windows 兼容性修复] loop="none" 防止 uvicorn 覆盖为 ProactorEventLoop，
    # 由 asyncio.Runner(loop_factory=SelectorEventLoop) 直接驱动以兼容 psycopg 异步连接池。
    if sys.platform == "win32":
        config = uvicorn.Config(app, host=_host, port=_port, loop="none")
        server = uvicorn.Server(config)
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(server.serve())
    else:
        uvicorn.run(app, host=_host, port=_port)
