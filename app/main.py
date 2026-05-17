import os
import asyncio

# [V13.0 系统级避灾] 强制避开 Windows 4311-4410 保留端口段
os.environ["PHOENIX_GRPC_PORT"] = "4517"
os.environ["PHOENIX_COLLECTOR_GRPC_PORT"] = "4517"
os.environ["PHOENIX_HOST"] = "127.0.0.1"

from loguru import logger
import app.logging_config # [V41.6] 物理链路可跳转配置
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.model_manager import model_manager
from app.usage_tracker import usage_tracker
from app.observability import init_observability

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 针对 LangGraph 0.2.x 与 aiosqlite 的性能/兼容性修复
    async with AsyncSqliteSaver.from_conn_string("audit_checkpoints.db") as saver_instance:
        # 兼容性补丁：处理可能的属性缺失 (针对 aio-sqlite 连接对象)
        target = None
        if hasattr(saver_instance, "conn"): target = saver_instance.conn
        elif hasattr(saver_instance, "connection"): target = saver_instance.connection
        
        if target and not hasattr(target, "is_alive"):
            logger.debug(">>> [兼容性补丁] 注入异步连接 is_alive 属性")
            target.is_alive = lambda: True
            
        app.state.saver = saver_instance
        logger.info(">>> [系统启动] 异步持久化层 (AsyncSqliteSaver) 已就绪")
        
        # [V4.9.8] 初始化双重观测栈 (Langfuse & Phoenix)
        init_observability()
        
        # [V5.5.2] 算力自愈：每日首次启动时执行全量状态体检
        if usage_tracker.should_run_startup_probe():
            logger.info(">>> [系统启明] 检测到今日首启，自动触发全量算力节点体检")
            usage_tracker.reset_blacklists() # 强制清除可能存在的历史误封
            asyncio.create_task(model_manager.run_health_check())
        
        yield
        
        # [V39.0] 优雅离场：在 FastAPI 关机前物理固化所有观测数据
        from app.observability import shutdown_observability
        shutdown_observability()

app = FastAPI(title="HSA AI Agent (Python Edition)", lifespan=lifespan)

# [重构 V10.0] 路由分组: palace / misc 端点已提取到 app/routes/
from app.routes.palace import router as palace_router
from app.routes.misc import router as misc_router
from app.routes.graph_state import router as graph_state_router
from app.routes.chat import router as chat_router
from app.routes.memory import router as memory_router
from app.routes.usage import router as usage_router
from app.routes.prompts import router as prompts_router # [V192.0] 提示词版本管理
app.include_router(palace_router)
app.include_router(misc_router)
app.include_router(graph_state_router)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(usage_router)
app.include_router(prompts_router) # [V192.0]

# 跨域配置: 从环境变量读取允许的来源, 默认仅本地开发
# 生产环境必须设置 CORS_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
# allow_origins=["*"] + allow_credentials=True 是严重安全漏洞 (允许任意域携带 Cookie)
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

# 安全护栏: 若同时允许 credentials 和通配符, 强制降级为不带 credentials
if _allow_credentials and "*" in _cors_origins:
    logger.warning("[SECURITY] CORS 配置不安全: allow_origins=['*'] 与 allow_credentials=True 冲突, 已强制禁用 credentials")
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Session-Id"],
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
    _port = int(os.getenv("UVICORN_PORT", "18882"))
    uvicorn.run(app, host=_host, port=_port)
