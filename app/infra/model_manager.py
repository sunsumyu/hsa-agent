"""
app/infra/model_manager.py
==========================
[V66.0 / Matt Pocock Deep Module / Facade] 模型管理器与智能路由中枢
负责全局算力池端点寻址、自适应降级链路构建、本地语义路由与复杂度启发式分级。
底层解耦委托至专用深模块：
- LLMFactory (模型实例创建与凭据解析)
- EndpointProber (主动探活与故障自愈)
- ComplexityClassifier (启发式复杂度分类)
- LocalServiceDetector (本地服务零配置发现)
- ModelPoolRouter (算力池寻址与角色降级路由)
"""

import os
import json
from loguru import logger
from typing import Dict, Optional, List, Any
from dotenv import load_dotenv

from app.core.schemas import ModelConfig
from app.infra.usage_tracker import usage_tracker
from app.infra.endpoint_pool_manager import endpoint_pool_manager
from app.infra.enriched_llm import Reranker
from app.infra.llm_factory import LLMFactory
from app.infra.endpoint_prober import EndpointProber
from app.infra.complexity_classifier import ComplexityClassifier
from app.infra.local_service_detector import LocalServiceDetector
from app.infra.model_pool_router import ModelPoolRouter

load_dotenv()


class ModelManager:
    """全局模型管理与角色动态路由门面深模块"""

    # 保留类属性兼容性
    _COMPLEX_SIGNALS = ComplexityClassifier._COMPLEX_SIGNALS
    _SIMPLE_SIGNALS = ComplexityClassifier._SIMPLE_SIGNALS

    def __init__(self, config_path: str = "configs/llm_providers.json"):
        self.config_path = config_path
        self.providers: Dict[str, ModelConfig] = self._load_config()
        self._local_embedder = None

        # 组合专职深模块
        self._factory = LLMFactory()
        self._prober = EndpointProber(factory=self._factory)
        self._router = ModelPoolRouter(
            pool_manager=endpoint_pool_manager,
            usage_tracker=usage_tracker,
            llm_factory=self._factory,
        )

        # 自动探测并网本地模型
        self.providers = LocalServiceDetector.discover_local_services(self.providers)

    @property
    def async_client(self):
        """代理访问全局共享异步 HTTP 客户端"""
        return self._factory.async_client

    @property
    def local_embedder(self):
        """延迟加载本地嵌入式语义模型"""
        if self._local_embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._local_embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
                logger.info("✅ [本地模型] 已延迟加载嵌入式语义路由引擎 (MiniLM-L12)")
            except Exception as e:
                logger.warning(f"本地语义模型加载失败: {e}，将回退至通用模式")
        return self._local_embedder

    def classify_complexity_locally(self, text: str) -> str:
        """启发式复杂度分类 (委托至 ComplexityClassifier)"""
        return ComplexityClassifier.classify(text)

    def _load_config(self) -> Dict[str, ModelConfig]:
        try:
            if not os.path.exists(self.config_path):
                return {}
            with open(self.config_path, "r", encoding="utf-8-sig") as f:
                raw_data = json.load(f)
                return {k: ModelConfig(**v) for k, v in raw_data.items()}
        except Exception as e:
            logger.error(f"加载模型注册表失败: {e}")
            return {}

    def _resolve_credentials(self, cfg: Any):
        """代理委托工厂解析环境变量凭据"""
        return self._factory.resolve_credentials(cfg)

    def _create_llm(self, name: str, cfg: Any, bypass_limit: bool = False):
        """代理委托工厂创建模型客户端"""
        return self._factory.create_llm(name, cfg)

    def _discover_and_register_local_services(self):
        """兼容保留：委托至 LocalServiceDetector"""
        self.providers = LocalServiceDetector.discover_local_services(self.providers)

    def get_model_list(self) -> List[Dict[str, Any]]:
        """获取所有可用模型列表及其健康状态"""
        all_models = []
        for k, cfg in self.providers.items():
            is_safe, _, _, _ = usage_tracker.check_limit(k)
            if not is_safe:
                continue
            stability = usage_tracker.get_stability_score(k)
            available = stability > 0.2
            all_models.append({
                "id": k,
                "name": cfg.model_name,
                "provider": cfg.provider,
                "tools_support": cfg.tools_support,
                "priority": cfg.priority,
                "is_available": available,
                "status_msg": "在线" if available else "稳定性差",
            })
        return all_models

    def get_adaptive_llm(self, model_id: Optional[str] = None, require_tools: bool = True):
        """获取自适应降级 LLM 实例 (委托至 ModelPoolRouter)"""
        return self._router.get_adaptive_llm(model_id=model_id, require_tools=require_tools)

    def _get_llm_from_pool(self, pool_id: str):
        """从指定算力池中挑选最优端点与备用降级链 (委托至 ModelPoolRouter)"""
        return self._router.get_llm_from_pool(pool_id)

    async def get_llm_by_role(self, role: str, retry_count: int = 0, config: Optional[Dict] = None):
        """异步高可用角色路由 (委托至 ModelPoolRouter)"""
        return await self._router.get_llm_by_role(role=role, retry_count=retry_count, config=config)

    def get_reranker(self, reranker_id: str = "gte-rerank") -> Optional[Reranker]:
        """获取语义重排器实例"""
        cfg = self.providers.get(reranker_id)
        if not cfg:
            for k, v in self.providers.items():
                if "rerank" in k.lower():
                    cfg = v
                    reranker_id = k
                    break
        return Reranker(reranker_id, cfg) if cfg else None

    async def probe_all_endpoints(self):
        """委托端点探活器进行全量节点拨测"""
        return await self._prober.probe_all_endpoints()

    async def _probe_single_endpoint(self, ep_id: str, ep: Any) -> bool:
        """委托端点探活器进行单节点拨测"""
        return await self._prober._probe_single_endpoint(ep_id, ep)

    async def run_health_check(self):
        """委托端点探活器运行周期性健康检查循环"""
        return await self._prober.run_health_check()


# 模块级单例代理 (通过 DI 容器延迟加载)
from app.core.container import LazyProxy

model_manager = LazyProxy("model_manager")
