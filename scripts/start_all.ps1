<#
.SYNOPSIS
    一键启动 Argus-Agent 后端 (18883) 与 Argus-Frontend 前端 (8888)，并自动打开法律辩法页面。
.EXAMPLE
    .\scripts\start_all.ps1
    .\scripts\start_all.ps1 -NoBrowser
#>
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"

$BackendDir = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path (Split-Path -Parent $BackendDir) "argus-frontend"
if (-not (Test-Path $FrontendDir)) {
    $FrontendDir = "F:\chain\argus-frontend"
}

$PythonExe = "G:\Hermes\hermes-agent\venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

function Stop-PortProcess([int]$Port) {
    $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
    foreach ($line in $lines) {
        if ($line -match "\s+(\d+)$") {
            $pidToKill = [int]$Matches[1]
            if ($pidToKill -gt 0) {
                Write-Host "[清理] 发现端口 $Port 被 PID=$pidToKill 占用，正在关闭旧进程..." -ForegroundColor Yellow
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Argus Legal & Audit 一键启动脚本" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

if (-not (Test-Path $FrontendDir)) {
    Write-Host "[错误] 未找到前端目录: $FrontendDir" -ForegroundColor Red
    exit 1
}

# 1. 清理旧端口占用，避免端口冲突
Stop-PortProcess -Port 18883
Stop-PortProcess -Port 8888
Start-Sleep -Milliseconds 500

# 2. 启动后端窗口 (端口 18883)
Write-Host "[1/2] 正在启动后端服务 (http://127.0.0.1:18883)..." -ForegroundColor Green
$BackendCmd = "cd /d `"$BackendDir`" && title Argus-Backend (18883) && `"$PythonExe`" -m app.main"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $BackendCmd -WorkingDirectory $BackendDir

# 3. 启动前端窗口 (端口 8888)
Write-Host "[2/2] 正在启动前端服务 (http://127.0.0.1:8888)..." -ForegroundColor Green
$FrontendNotice = "echo [提示] 前端服务启动中... 注意：请勿用鼠标点击此黑框(否则Windows会进入选择暂停模式，若误点请按键盘 Esc 键解除)"
$FrontendCmd = "cd /d `"$FrontendDir`" && title Argus-Frontend (8888) && $FrontendNotice && trunk serve --port 8888 --address 127.0.0.1 --disable-address-lookup --skip-version-check"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $FrontendCmd -WorkingDirectory $FrontendDir

# 4. 等待后端与前端就绪并打开浏览器
if (-not $NoBrowser) {
    Write-Host "正在等待服务完全就绪 (等待期间请勿点击黑框)..." -ForegroundColor Gray
    
    # 4.1 等待后端 (18883)
    $backendReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:18883/agent/models" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                $backendReady = $true
                break
            }
        } catch {}
    }
    if ($backendReady) {
        Write-Host "✅ [1/2] 后端服务已就绪 (http://127.0.0.1:18883)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ 后端服务初始化中..." -ForegroundColor Yellow
    }

    # 4.2 等待前端 (8888) 监听
    Write-Host "正在等待前端服务响应 (8888 端口)..." -ForegroundColor Gray
    $frontendReady = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        try {
            $rf = Invoke-WebRequest -Uri "http://127.0.0.1:8888/" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($rf.StatusCode -eq 200) {
                $frontendReady = $true
                break
            }
        } catch {}
    }

    if ($frontendReady) {
        Write-Host "✅ [2/2] 前端服务已就绪 (8888)，正在打开浏览器: http://localhost:8888/legal" -ForegroundColor Green
        Start-Process "http://localhost:8888/legal"
    } else {
        Write-Host "⚠️ 前端 8888 启动超时，自动通过后端备用端点打开: http://localhost:18883/legal" -ForegroundColor Yellow
        Start-Process "http://localhost:18883/legal"
    }
}

Write-Host "启动流程已完成！关闭弹出的两个控制台窗口即可停止服务。" -ForegroundColor Cyan
