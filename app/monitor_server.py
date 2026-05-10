from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import json
import os
import time
from datetime import datetime
from app.usage_tracker import usage_tracker
from app.endpoint_pool_manager import endpoint_pool_manager
from loguru import logger

app = FastAPI(title="HSA Model Operations Center")

# --- 数据接口 ---

@app.get("/api/status")
async def get_status():
    """获取所有节点的实时监控指标"""
    # [V8.0] 从 SQLite 物理数据库加载（增量安全，不会被覆盖）
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "cloud_discovery.db")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, platform, remaining, total, status, hint FROM models ORDER BY status DESC, name").fetchall()
        free_discovery = [dict(r) for r in rows]
        conn.close()
    except Exception as e:
        free_discovery = []
        logger.error(f"Error loading discovery DB: {e}")

    # 刷新一次稳定性分（从内存同步到对象）
    for ep_id, state in endpoint_pool_manager.states.items():
        state.refresh_stability()
    
    stats_data = usage_tracker.stats
    pools_data = endpoint_pool_manager.pools
    states_data = endpoint_pool_manager.states
    
    nodes_by_tier = {"core": [], "backup": []}
    for ep_id, state in states_data.items():
        # 获取用量数据
        daily_tokens = stats_data.daily_usage.get(ep_id, 0)
        daily_reqs = stats_data.daily_requests.get(ep_id, 0)
        
        # 获取分钟级实时数据
        current_min = datetime.now().strftime("%Y-%m-%d %H:%M")
        rpm = usage_tracker.rpm_window.get(ep_id, {}).get(current_min, 0)
        tpm = usage_tracker.tpm_window.get(ep_id, {}).get(current_min, 0)
        
        # 冷却状态
        now = time.time()
        is_cooling = state.is_cooling and now < state.cooldown_until
        cooldown_remaining = max(0, int(state.cooldown_until - now)) if is_cooling else 0
        
        # [V7.6] 增强型模糊匹配：优先寻找精确匹配，找不到则尝试关键片段匹配
        ep_id_clean = ep_id.lower().replace("-bailian", "").replace("-volc", "")
        cloud_info = next((item for item in free_discovery if ep_id_clean in item['name'].lower() or item['name'].lower() in ep_id_clean), None)
        
        node_info = {
            "id": ep_id,
            "provider": state.config.provider,
            "platform": state.config.platform,
            "model_name": state.config.model_name,
            "weight": state.config.weight,
            "stability": state.stability,
            "is_cooling": is_cooling,
            "cooldown_remaining": cooldown_remaining,
            "daily_tokens": daily_tokens,
            "daily_quota": state.config.daily_quota,
            "token_usage_pct": round((daily_tokens / state.config.daily_quota * 100), 2) if state.config.daily_quota > 0 else 0,
            "daily_reqs": daily_reqs,
            "rpm": rpm,
            "tpm": tpm,
            "rpm_limit": state.config.rpm_limit,
            "tpm_limit": state.config.tpm_limit,
            "cloud_remaining": cloud_info['remaining'] if cloud_info else None,
            "cloud_total": cloud_info['total'] if cloud_info else None,
            "cloud_status": cloud_info.get('status', 'OK') if cloud_info else 'OK'
        }
        
        # 按池的名称简单判定核心还是备用
        is_core = any("tier-1" in p_id for p_id, p_cfg in pools_data.items() if ep_id in [e.id for e in p_cfg.endpoints])
        if is_core:
            nodes_by_tier["core"].append(node_info)
        else:
            nodes_by_tier["backup"].append(node_info)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "today": stats_data.today,
        "tiers": nodes_by_tier,
        "discovery": free_discovery,
        "total_models": len(free_discovery),
        "pools": {k: {"display_name": v.display_name, "endpoints": [e.id for e in v.endpoints]} for k, v in pools_data.items()}
    }

@app.post("/api/reset")
async def reset_circuit_breaker():
    """手动重置全量黑名单"""
    try:
        usage_tracker.reset_blacklists()
        for state in endpoint_pool_manager.states.values():
            state.is_cooling = False
            state.cooldown_until = 0.0
        return {"status": "success", "message": "全量算力节点已复活"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return f.read()

def run_monitor(port: int = 8089):
    os.makedirs("app/static", exist_ok=True)
    logger.info(f"🚀 [MOC] 算力管理中心正在启动: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run_monitor()
