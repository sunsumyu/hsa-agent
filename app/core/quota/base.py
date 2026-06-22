from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from loguru import logger

class BaseQuotaFetcher(ABC):
    """[V180.0] 云端配额获取器基类 - 企业级标准接口"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    @abstractmethod
    async def fetch_quota(self, model_id: str) -> Optional[int]:
        """
        从云端获取剩余配额 (Tokens)
        返回: 剩余 Token 数，若获取失败返回 None
        """
        pass

    @abstractmethod
    async def get_real_time_usage(self, model_id: str) -> Optional[int]:
        """
        从云端获取今日已用量 (Tokens)
        """
        pass
