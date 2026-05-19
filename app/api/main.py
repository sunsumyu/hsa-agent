# [企业级自愈] 兼容外部启动脚本与旧版路径约束
# 该跳板模块用于解决 uvicorn app.api.main:app 启动时的 ModuleNotFoundError。
# 实际的核心 ASGI 实例位于 app/main.py 中。

from app.main import app

if __name__ == "__main__":
    import uvicorn
    import os
    _host = os.getenv("UVICORN_HOST", "127.0.0.1")
    _port = int(os.getenv("UVICORN_PORT", "8000"))
    uvicorn.run(app, host=_host, port=_port)
