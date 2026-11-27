---
name: argus-runbook
description: 在本地启动 Argus-Agent 后端、前端或 ClickHouse，或遇到 Windows 事件循环、保留端口、代理环境变量、CMD 黑框挂起及端口冲突报错时查阅。
---

# Argus-Agent 本地环境与启动排障手册

## 高频踩坑与确定性解法

### 1. `ProactorEventLoop` / `WinError 10014` 导致 `psycopg` 异步连接池报错
- **症状**：裸跑 `uvicorn app.main:app` 启动时，`AsyncConnectionPool` 报 `ProactorEventLoop` 不兼容或指针异常。
- **根因**：Windows 默认事件循环为 `ProactorEventLoop`，且 `uvicorn` 默认 `loop` 参数会覆盖循环策略。
- **解法**：始终通过 `python -m app.main` 启动（内部先设 `WindowsSelectorEventLoopPolicy` 并以 `loop="none"` + `SelectorEventLoop` 驱动）。

### 2. Windows 保留端口段 `4311–4410` 阻塞 Phoenix gRPC 启动
- **症状**：可观测组件启动绑定 gRPC 端口失败或权限被拒。
- **根因**：Hyper-V/WSL 在 Windows 上动态保留 `4311–4410` TCP 端口段。
- **解法**：`app/main.py` 已显式固定 `PHOENIX_GRPC_PORT=4517` 与 `PHOENIX_COLLECTOR_GRPC_PORT=4517`；外部脚本覆盖环境变量时需避开保留段。

### 3. `18883` / `8888` / `8223` / `9002` 端口占用导致白屏或启动失败
- **症状**：服务启动报端口已占用、浏览器打开白屏或请求打到旧进程。
- **根因**：旧后端/前端进程残留监听，未释放端口。
- **解法**：先查占用并清理（`netstat -ano | findstr ":18883 :8888"`），或直接执行 `.\scripts\start_all.ps1` 自动回收旧 PID；严禁在白屏时盲目循环重开浏览器。

### 4. Windows CMD 黑框误点击导致前后端“假死”
- **症状**：通过 `start_all.bat` 弹出的服务窗口长时间无日志输出、请求超时。
- **根因**：Windows 控制台“快速编辑模式”下鼠标点击会阻塞标准输出。
- **解法**：选中对应 CMD 窗口按 `Esc` 键解除选择，避免用鼠标点击运行中的日志框。

### 5. 评测脚本受本地代理或 HuggingFace 联网阻塞
- **症状**：运行 Benchmark 时报代理连接失败或 `SentenceTransformer` 卡在下载校验。
- **根因**：终端继承系统代理环境变量，或未启用离线模型缓存。
- **解法**：参考 `scripts/run_v6_user_perspective_benchmark.py`，启动前清空 `HTTP_PROXY`/`HTTPS_PROXY` 并设置 `NO_PROXY=*`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`。

## 标准一键启动命令（Golden Commands）

```powershell
# 1. 启动本地只读保护 ClickHouse 容器（端口 8223 / 9002）
.\scripts\start_clickhouse_docker.ps1

# 2. 仅启动后端 API（18883）
python -m app.main

# 3. 一键清理端口并拉起后端（18883）+ 前端（8888，不自动弹窗）
.\scripts\start_all.ps1 -NoBrowser
```
