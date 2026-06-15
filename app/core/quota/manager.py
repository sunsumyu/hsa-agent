from typing import Dict, Any, List
from loguru import logger
from app.core.quota.base import BaseQuotaFetcher
from app.core.quota.volcengine import VolcengineQuotaFetcher
from app.core.quota.bailian import BailianQuotaFetcher

class QuotaSyncManager:
    """[V180.0] 企业级配额同步管理中枢"""
    
    def __init__(self):
        self.fetchers: Dict[str, BaseQuotaFetcher] = {
            "volcengine": VolcengineQuotaFetcher(),
            "bailian": BailianQuotaFetcher()
        }

    async def sync_all(self):
        """执行全平台配额深穿透同步"""
        from app.infra.usage_tracker import usage_tracker
        logger.info("📡 [QuotaSync] 正在启动全平台云端配额同步...")
        
        for model_id, cfg in usage_tracker.model_configs.items():
            provider = cfg.provider.lower()
            if provider in self.fetchers:
                fetcher = self.fetchers[provider]
                try:
                    quota = await fetcher.fetch_quota(model_id)
                    if quota is not None:
                        usage_tracker.cloud_remaining_tokens[model_id] = quota
                        logger.debug(f"[QuotaSync] {model_id} ({provider}) 剩余额度: {quota}")
                except Exception as e:
                    logger.error(f"[QuotaSync] {model_id} 同步失败: {e}")
            
        logger.success("✅ [QuotaSync] 云端数据同步完成。")

# 单例导出
quota_manager = QuotaSyncManager()
