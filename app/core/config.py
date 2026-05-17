"""
app/core/config.py
===================
[V161.0] 工业级全局配置中心 (Global Settings)

基于 Pydantic 实现，支持环境变量自动映射、类型校验及默认值保护。
"""

import os
from typing import Optional, List
from pydantic import Field

# [V4.5.4] 物理环境全局配置中心
# ---------------------------------------------------------
# [V4.5.6] 物理固化完成：恢复离线模式，确保零延迟运行
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
# ---------------------------------------------------------

from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger

class GlobalSettings(BaseSettings):
    """
    HSA-Agent 全局配置模型
    """
    # --- 系统基础配置 ---
    app_name: str = "HSA-Agent-Industrial"
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    memory_mode: str = Field(default="LOCAL")  # [V4.5] 记忆模式：LOCAL | ENTERPRISE
    
    # --- LLM 默认行为配置 ---
    # 这些是当具体模型配置缺失时的全局兜底值
    default_temperature: float = 0.3
    default_max_tokens: int = 4096
    enable_semantic_cache: bool = True
    
    # --- 审计策略与安全红线 ---
    sql_row_tolerance: int = 1000        # SQL 结果集容差（触发警告的阈值）
    max_agent_retries: int = 3          # Agent 自愈最大重试次数
    hitl_risk_threshold: float = 0.6    # 触发人工审批的风险分数阈值
    
    # --- 物理基础设施 ---
    redis_url: str = "redis://localhost:6379/0"
    clickhouse_host: str = "localhost"
    
    # --- 环境变量配置 (Pydantic 特性) ---
    # 自动搜索以 HSA_ 开头的环境变量，例如 HSA_LOG_LEVEL -> log_level
    model_config = SettingsConfigDict(
        env_prefix="HSA_", 
        env_file=".env", 
        extra="ignore"
    )

# 实例化全局单例
settings = GlobalSettings()

def reload_settings():
    """手动刷新配置（用于热更新场景）"""
    global settings
    settings = GlobalSettings()
    logger.info("♻️ [Config] 全局配置已刷新")

# 延迟导入以避免循环依赖
logger.info(f"⚙️ [Config] 配置中心已就绪 | Debug: {settings.debug} | LogLevel: {settings.log_level}")
