import os
import sys
import json
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())

from app.usage_tracker import usage_tracker

def debug_usage_tracker():
    print("\n>>> [UsageTracker 深度诊断] 检查算力可用性...")
    
    models_to_check = ["qwen-plus", "qwen-turbo", "doubao-pro-32k"]
    
    for m_id in models_to_check:
        is_safe, usage, quota, reason = usage_tracker.check_limit(m_id)
        config = usage_tracker.model_configs.get(m_id)
        
        print(f"\n--- 节点: {m_id} ---")
        print(f"配置是否存在: {config is not None}")
        if config:
            print(f"配置详情: provider={config.provider}, model_name={config.model_name}, quota={config.daily_quota}")
        print(f"可用性检测: {'OK' if is_safe else 'FAILED'}")
        print(f"用量情况: {usage} / {quota}")
        if not is_safe:
            print(f"不可用原因: {reason}")
            
    # 打印黑名单情况
    print("\n--- 黑名单/冷却状态 ---")
    print(json.dumps(usage_tracker.stats.blacklist_expiry, indent=2))

if __name__ == "__main__":
    debug_usage_tracker()
