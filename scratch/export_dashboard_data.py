import json
import os
from datetime import datetime

def export():
    # 1. 加载用量数据
    usage_path = "data/usage_stats.json"
    usage_data = {}
    if os.path.exists(usage_path):
        with open(usage_path, 'r', encoding='utf-8') as f:
            usage_data = json.load(f)
    
    # 2. 加载数据库中的物理节点配置 (V178.9)
    import sqlite3
    from app.infra.usage_tracker import usage_tracker
    endpoint_configs = []
    db_path = "data/memory_v3/episodic.db"
    if os.path.exists(db_path):
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM endpoint_configs").fetchall()
                for r in rows:
                    node = dict(r)
                    # 注入预测数据 (V180.0)
                    node["rounds_left"] = usage_tracker.get_burnout_prediction(node["id"])
                    endpoint_configs.append(node)
        except Exception as e:
            print(f"Failed to fetch endpoint_configs: {e}")

    # 3. 构造门户展示数据
    portal_data = {
        "update_time": datetime.now().isoformat(),
        "memory_health": {
            "episodic_count": 12,
            "semantic_nodes": 178,
            "alignment_rate": 0.994
        },
        "endpoints": endpoint_configs,
        "performance": bench_data,
        "usage": usage_data
    }
    
    os.makedirs("data", exist_ok=True)
    with open("data/portal_data.json", 'w', encoding='utf-8') as f:
        json.dump(portal_data, f, indent=2, ensure_ascii=False)
    
    print("✅ Dashboard data exported to data/portal_data.json")

if __name__ == "__main__":
    export()
