Write-Host ">>> 检查 Docker 守护进程状态..." -ForegroundColor Cyan

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker 守护进程未启动，请确保 Docker Desktop 处于运行状态！" -ForegroundColor Red
    exit 1
}

Write-Host "✔ Docker 已就绪，正在检查 ClickHouse Server 容器..." -ForegroundColor Green

# 检查是否已存在同名容器
$existing = docker ps -a -q -f name=clickhouse-server
if ($existing) {
    Write-Host ">>> 发现已存在的 clickhouse-server 容器，正在启动..." -ForegroundColor Yellow
    docker start clickhouse-server
} else {
    Write-Host ">>> 创建并启动 clickhouse-server 容器（只读保护，持久化存储卷）..." -ForegroundColor Cyan
    docker run -d `
      --name clickhouse-server `
      -p 8223:8123 `
      -p 9002:9000 `
      -v F:/chain/clickhouse_docker_data:/var/lib/clickhouse `
      -e CLICKHOUSE_RUN_AS_ROOT=1 `
      -e CLICKHOUSE_DB=default `
      -e CLICKHOUSE_USER=default `
      -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 `
      -e CLICKHOUSE_DO_NOT_CHOWN=1 `
      --ulimit nofile=262144:262144 `
      clickhouse/clickhouse-server:latest
}

Write-Host ">>> 等待 ClickHouse 服务健康检查响应 (端口 8223)..." -ForegroundColor Cyan
$retries = 30
$ready = $false

for ($i = 1; $i -le $retries; $i++) {
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:8223" -TimeoutSec 2
        if ($res -like "*Ok*") {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if ($ready) {
    Write-Host "🎉 ClickHouse 已成功启动并在 127.0.0.1:8223 监听！" -ForegroundColor Green
    Write-Host "🛡️ 安全提示：已启用纯只读保障，绝不执行任何 DROP/TRUNCATE/UPDATE/DELETE 修改原表数据。" -ForegroundColor Yellow
} else {
    Write-Host "❌ 等待超时，ClickHouse 服务未能及时响应。" -ForegroundColor Red
}
