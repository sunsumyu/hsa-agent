import json
import os

stats_path = "data/usage_stats.json"

def reset_stats():
    if os.path.exists(stats_path):
        with open(stats_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"清理前的黑名单: {data.get('blacklist_expiry')}")
        
        # 强制清空
        data['blacklist_expiry'] = {}
        data['daily_usage'] = {}
        data['daily_requests'] = {}
        
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print("✅ 状态文件已物理重置。")
    else:
        print("文件不存在，无需重置。")

if __name__ == "__main__":
    reset_stats()
