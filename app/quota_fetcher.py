import os
import requests
import json
from loguru import logger
from datetime import datetime

def fetch_deepseek_balance():
    """获取 DeepSeek 余额"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    
    url = "https://api.deepseek.com/user/balance"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("is_available"):
                balance = data.get("balance_infos", [{}])[0].get("total_balance", "0")
                logger.info(f"[QuotaFetcher] DeepSeek 余额: {balance}")
                return float(balance)
        return None
    except Exception as e:
        logger.error(f"DeepSeek 余额查询失败: {e}")
        return None

def fetch_volcengine_usage(model_id: str):
    """
    获取火山引擎(Ark)用量。
    注意：此接口通常需要不同的 AccessKey/SecretKey，
    目前的 ARK_API_KEY 仅用于推理。此处建议优先使用微探测结果作为健康指标。
    """
    # 占位符逻辑，若后续用户提供 IAM Key 可完整实现
    return None

def sync_all_quotas():
    """将所有平台的物理限额同步至本地 UsageTracker"""
    logger.info(">>> [架构自愈] 正在启动物理配额同步...")
    
    # 示例：DeepSeek 同步
    ds_balance = fetch_deepseek_balance()
    if ds_balance is not None and ds_balance <= 0.01:
        logger.warning("!!! [余额预警] DeepSeek 余额不足，标记为不可用 !!!")
        from app.usage_tracker import usage_tracker
        usage_tracker.blacklist_model("deepseek-r1", "Account Balance Exhausted", permanent=True)

if __name__ == "__main__":
    sync_all_quotas()
