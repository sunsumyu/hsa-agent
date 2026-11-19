#!/usr/bin/env python3
"""
启动脚本 - 修复 Windows + Python 3.11 的 asyncio 问题
"""
import sys
import os

# [关键修复] 在导入任何异步库之前设置事件循环策略
if sys.platform == "win32":
    import asyncio
    # 强制使用 SelectorEventLoop 替代 ProactorEventLoop
    # 注意：必须在任何异步操作之前设置
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 创建并设置事件循环
    loop = asyncio.SelectorEventLoop()
    asyncio.set_event_loop(loop)

# 现在可以导入其他模块了
os.environ["PHOENIX_GRPC_PORT"] = "4517"
os.environ["PHOENIX_COLLECTOR_GRPC_PORT"] = "4517"
os.environ["PHOENIX_HOST"] = "127.0.0.1"

from loguru import logger

if __name__ == "__main__":
    host = os.getenv("UVICORN_HOST", "127.0.0.1")
    port = int(os.getenv("UVICORN_PORT", "18883"))  # 改为 18883 避免端口冲突

    print(f">>> 正在启动服务器 http://{host}:{port}")
    print(f">>> 使用事件循环策略: {asyncio.get_event_loop_policy().__class__.__name__}")

    # 使用更底层的 uvicorn 配置
    from uvicorn import Config, Server

    # 关键：支持热重载或标准事件循环
    config = Config(
        app="app.main:app",
        host=host,
        port=port,
        loop="asyncio",
        reload=True,
        access_log=True
    )

    server = Server(config=config)

    # 在当前事件循环中运行
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(server.serve())
    finally:
        loop.close()
