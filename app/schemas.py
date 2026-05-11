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

# ──────────────────────────────────────────────────────────────
# [重构 V90.0] 提取 ModelConfig 与 EndpointConfig 的公共字段
# ──────────────────────────────────────────────────────────────
# 历史包袱: ModelConfig(19字段) 和 EndpointConfig(15字段) 有 11 个字段
# 逐字段完全一致, 2 个默认值不同 (rpm_limit / tpm_limit), 其余各自独有。
# 现在提取 ProviderAttributes 基类, 子类只声明增量字段 + 覆盖默认值。
# 向后兼容: 字段名/类型全部保留, 现有代码无需修改。
# ──────────────────────────────────────────────────────────────

class ProviderAttributes(BaseModel):
    """大模型供应商通用属性 (ModelConfig 与 EndpointConfig 的公共基类)。"""
    # 身份识别
    provider: str
    model_name: str
    family: Optional[str] = None
    platform: Optional[str] = None
    # 认证凭据
    api_key_env: str
    base_url_env: Optional[str] = None
    # 配额 (默认值子类可覆盖)
    daily_quota: int = 10000000
    rpd_limit: int = 1500
    rpm_limit: int = 60  # 基线值, ModelConfig 会覆盖为 15
    tpm_limit: int = 100000  # 基线值, ModelConfig 会覆盖为 250000
    # 成本计量
    input_cost_1k: float = 0.0
    output_cost_1k: float = 0.0
    # 采样
    temperature: float = 0.3


class ModelConfig(ProviderAttributes):
    """单一模型的完整配置 (含运行时健康状态)。"""
    # 模型级专属字段
    priority: int = 0
    tools_support: bool = True
    is_active: bool = True
    # 覆盖基类默认值: ModelConfig 的 rpm/tpm 限制更严格
    rpm_limit: int = 15
    tpm_limit: int = 250000
    # 运行时健康追踪
    last_error: Optional[str] = None
    last_success_time: float = 0.0
    consecutive_failures: int = 0


class EndpointConfig(ProviderAttributes):
    """池化接入点配置 (一个模型可有多个 endpoint, 做负载均衡)。"""
    # Endpoint 级专属字段
    id: str
    weight: int = 50
    # rpm/tpm 采用基类默认值 (60 / 100000) — 池化场景限制更宽松

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
