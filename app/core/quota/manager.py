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
        from app.core.schemas import ModelConfig
        logger.info("📡 [QuotaSync] 正在启动全平台云端配额同步...")
        
        # 1. 动态发现火山引擎模型
        if "volcengine" in self.fetchers:
            try:
                if hasattr(self.fetchers["volcengine"], "discover_models"):
                    discovered_models = await self.fetchers["volcengine"].discover_models()
                    for m in discovered_models:
                        m_id = m.get("id")
                        if m_id and m_id not in usage_tracker.model_configs:
                            new_cfg = ModelConfig(
                                provider="volcengine",
                                platform="volcengine-dynamic",
                                model_name=m_id,
                                api_key_env="VOLC_API_KEY",
                                base_url_env="VOLC_BASE_URL",
                                daily_quota=1000000,
                                rpm_limit=1000,
                                tpm_limit=100000
                            )
                            usage_tracker.model_configs[m_id] = new_cfg
            except Exception as e:
                logger.error(f"[QuotaSync] 动态发现模型失败: {e}")

        # 2. 原有的额度同步逻辑
        for model_id, cfg in list(usage_tracker.model_configs.items()):
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
