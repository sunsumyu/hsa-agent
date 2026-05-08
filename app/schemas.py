from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any
from enum import Enum
import time

class AgentRole(str, Enum):
    PLANNER = "planner"
    CODER = "coder"
    REPORTER = "reporter"
    JUDGE = "judge"

class RoleConfig(BaseModel):
    primary: str
    secondary: Optional[str] = None
    tertiary: Optional[str] = None
    # Token 预算 (单次调用)
    max_input_tokens: int = 4000
    max_output_tokens: int = 2000

class ModelConfig(BaseModel):
    provider: str
    model_name: str
    priority: int = 0
    tools_support: bool = True
    temperature: float = 0.3
    api_key_env: str
    base_url_env: Optional[str] = None
    daily_quota: int = 10000000
    rpd_limit: int = 1500
    rpm_limit: int = 15
    tpm_limit: int = 250000
    input_cost_1k: float = 0.0
    output_cost_1k: float = 0.0
    is_active: bool = True
    last_error: Optional[str] = None
    last_success_time: float = 0.0
    consecutive_failures: int = 0

class EndpointConfig(BaseModel):
    """单个接入点配置"""
    id: str
    provider: str
    model_name: str
    api_key_env: str
    base_url_env: Optional[str] = None
    weight: int = 50
    daily_quota: int = 10000000
    rpd_limit: int = 1500
    rpm_limit: int = 60
    tpm_limit: int = 100000
    input_cost_1k: float = 0.0
    output_cost_1k: float = 0.0
    temperature: float = 0.3

class PoolConfig(BaseModel):
    """接入点池配置"""
    display_name: str
    tools_support: bool = True
    fallback_pool: Optional[str] = None
    endpoints: List[EndpointConfig]

class RoleConfigV2(BaseModel):
    """角色配置 V2 (池化版)"""
    pool: str
    max_input_tokens: int = 4000
    max_output_tokens: int = 2000

class UsageStats(BaseModel):
    today: str
    daily_usage: Dict[str, int] = Field(default_factory=dict)
    daily_requests: Dict[str, int] = Field(default_factory=dict)
    total_usage: Dict[str, int] = Field(default_factory=dict)
    blacklist_expiry: Dict[str, float] = Field(default_factory=dict)
    stability_scores: Dict[str, float] = Field(default_factory=dict)
    last_probe_date: Optional[str] = None
