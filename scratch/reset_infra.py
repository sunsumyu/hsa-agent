import sys
import os

# 确保能导入 app 模块
sys.path.append(os.getcwd())

from app.infra.usage_tracker import usage_tracker
from loguru import logger

def reset_infra():
    logger.info("🚀 正在执行算力基础设施强力自愈...")
    
    # 1. 清除黑名单
    usage_tracker.reset_blacklists()
    
    # 2. 恢复所有节点的健康分为 1.0
    for model_id in usage_tracker.stability_scores:
        usage_tracker.stability_scores[model_id] = 1.0
        
    # 3. 强制保存到磁盘
    usage_tracker._save_stats()
    
    logger.success("✅ 算力锁已解除！所有节点已重新上线。")
    logger.info("提示：如果是因为物理额度耗尽（真正的 403），重试可能依然会失败。但如果是 RPM/TPM 误伤，现在已经可以工作了。")

if __name__ == "__main__":
    reset_infra()
