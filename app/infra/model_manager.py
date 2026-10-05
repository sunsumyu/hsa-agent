import os
import json
import logging
import asyncio
from loguru import logger
from typing import Dict, Optional, List, Any
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
import requests
from app.infra.usage_tracker import usage_tracker
from app.infra.endpoint_pool_manager import endpoint_pool_manager
from app.infra.redis_client import redis_manager
from app.core.schemas import ModelConfig, EndpointConfig, RoleConfigV2
from app.core.observability import get_callbacks
from dotenv import load_dotenv

load_dotenv()
from app.infra.enriched_llm import EnrichedChatOpenAI, EnrichedChatGoogleGenerativeAI, EnrichedChatAnthropic, Reranker


class ModelManager:
    def __init__(self, config_path="configs/llm_providers.json"):
        self.config_path = config_path
        self.providers: Dict[str, ModelConfig] = self._load_config()
        self._local_embedder = None
        self._async_client = None
        # [V151.0] 启动自动探测引擎
        self._discover_and_register_local_services()

    @property
    def async_client(self):
        """[V142.0] 全局共享异步 HTTP 客户端：解决 Event loop is closed 报错并提升连接池性能"""
        import httpx
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        return self._async_client
        
    @property
    def local_embedder(self):
        if self._local_embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._local_embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("✅ [本地模型] 已延迟加载嵌入式语义路由引擎 (MiniLM-L12)")
            except Exception as e:
                logger.warning(f"本地语义模型加载失败: {e}，将回退至通用模式")
        return self._local_embedder

    # 复杂度判定的启发式信号 (从 SchemaRegistry 衍生)
    _COMPLEX_SIGNALS = (
        "团伙", "欺诈环", "共用", "联邦", "图谱", "多层关联",
        "跨机构", "跨年", "环路", "图分析", "graph", "fraud_ring",
    )
    _SIMPLE_SIGNALS = (
        "性别冲突", "重复收费", "查一下", "列出", "显示",
        "总数", "数量", "多少",
    )

    def classify_complexity_locally(self, text: str) -> str:
        """
        启发式复杂度分类。原版御宅式返回 MEDIUM, 导致 planner_light/heavy 路由失效。
        现按关键词信号 + 长度做出合理判断:
          - HIGH: 命中复杂信号 (团伙/联邦/图谱) 或 文本超长
          - LOW: 命中简单信号 (性别冲突/查一下) 且文本短
          - MEDIUM: 默认
        """
        if not text:
            return "MEDIUM"

        t = text.lower()
        # 高复杂度: 关键词 OR 任务文本超过 200 字符
        if any(s in text for s in self._COMPLEX_SIGNALS) or any(s in t for s in ("fraud_ring", "graph", "联邦")):
            return "HIGH"
        if len(text) > 200:
            return "HIGH"
        # 低复杂度: 关键词 AND 文本简短
        if any(s in text for s in self._SIMPLE_SIGNALS) and len(text) < 50:
            return "LOW"
        return "MEDIUM"
        
    def _load_config(self) -> Dict[str, ModelConfig]:
        try:
            if not os.path.exists(self.config_path): return {}
            with open(self.config_path, 'r', encoding='utf-8-sig') as f:
                raw_data = json.load(f)
                return {k: ModelConfig(**v) for k, v in raw_data.items()}
        except Exception as e:
            logger.error(f"加载模型注册表失败: {e}")
            return {}

    def _resolve_credentials(self, cfg: Any) -> tuple[Optional[str], Optional[str]]:
        """[V151.0] 智能凭证解析：支持特定环境变量与通用环境变量的层级打捞"""
        # 1. 优先尝试特定环境变量
        api_key = os.getenv(cfg.api_key_env)
        base_url = os.getenv(cfg.base_url_env) if hasattr(cfg, 'base_url_env') and cfg.base_url_env else None
        
        # 2. 如果缺失，尝试通用环境变量 LLM_API_KEY / LLM_BASE_URL
        if not api_key:
            api_key = os.getenv("LLM_API_KEY")
            if api_key: logger.info(f"💡 [SmartDiscovery] 节点 {cfg.model_name} 已通过通用密钥 LLM_API_KEY 激活")
            
        if not base_url and os.getenv("LLM_BASE_URL"):
            base_url = os.getenv("LLM_BASE_URL")
            logger.info(f"💡 [SmartDiscovery] 节点 {cfg.model_name} 已通过通用地址 LLM_BASE_URL 激活")
            
        return api_key, base_url

    def _discover_and_register_local_services(self):
        """[V151.0] 零配置本地服务探测：自动发现 Ollama/vLLM"""
        local_checks = [
            ("ollama", "http://localhost:11434/v1", "OLLAMA_API_KEY"),
            ("vllm", "http://localhost:8000/v1", "VLLM_API_KEY"),
        ]
        
        for name, url, key_env in local_checks:
            try:
                # 简单同步检查端口是否开放 (超时 0.5s)
                import socket
                from urllib.parse import urlparse
                parsed = urlparse(url)
                with socket.create_connection((parsed.hostname, parsed.port), timeout=0.5):
                    if name not in self.providers:
                        logger.success(f"🚀 [AutoDetect] 发现本地 {name} 服务在 {url} 运行，已自动并网。")
                        self.providers[name] = ModelConfig(
                            provider="openai",
                            model_name=os.getenv("LLM_MODEL_ID", "llama3"),
                            priority=5,
                            tools_support=True,
                            api_key_env=key_env,
                            base_url_env=f"LOCAL_{name.upper()}_URL",
                            daily_quota=999999
                        )
                        # 注入环境变量以便后续 _create_llm 正常工作
                        os.environ[f"LOCAL_{name.upper()}_URL"] = url
                        if not os.getenv(key_env): os.environ[key_env] = "sk-local-not-needed"
            except:
                pass

    def get_model_list(self):
        all_models = []
        for k, cfg in self.providers.items():
            is_safe, usage, quota, reason = usage_tracker.check_limit(k)
            if not is_safe: continue
            stability = usage_tracker.get_stability_score(k)
            available = stability > 0.2
            all_models.append({
                "id": k,
                "name": cfg.model_name,
                "provider": cfg.provider,
                "tools_support": cfg.tools_support,
                "priority": cfg.priority,
                "is_available": available,
                "status_msg": "在线" if available else "稳定性差"
            })
        return all_models

    def _create_llm(self, name: str, cfg: Any, bypass_limit: bool = False):
        provider = cfg.provider
        api_key, base_url = self._resolve_credentials(cfg)
        model_name = cfg.model_name
        temperature = getattr(cfg, 'temperature', 0.3)

        if not api_key:
            logger.warning(f"模型 {name} 缺少 API_KEY，跳过。")
            return None

        default_headers = {}
        if provider == "dashscope":
            default_headers["x-dashscope-sse"] = "enable"
        
        try:
            if provider == "google":
                return EnrichedChatGoogleGenerativeAI(
                    model=model_name,
                    api_key=api_key, 
                    google_api_key=api_key,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    endpoint_id=name
                )
            elif provider == "anthropic":
                base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "http://103.236.76.197:11223/anthropic")
                return EnrichedChatAnthropic(
                    model_name=model_name,
                    anthropic_api_key=api_key,
                    anthropic_api_url=base_url,
                    temperature=temperature,
                    timeout=120.0,
                    streaming=True,
                    endpoint_id=name
                )
            else:
                return EnrichedChatOpenAI(
                    model=model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    default_headers=default_headers,
                    http_async_client=self.async_client,  # [V142.0] 注入共享客户端
                    endpoint_id=name
                )
        except Exception as e:
            logger.error(f"LLM 实例化失败: {name} | {e}")
            return None

    def get_adaptive_llm(self, model_id: Optional[str] = None, require_tools: bool = True):
        if model_id:
            for pool in endpoint_pool_manager.pools.values():
                for ep in pool.endpoints:
                    if ep.id == model_id or ep.model_name == model_id:
                        return self._create_llm(ep.id, ep), ep.id
        pool_id = "tier-1-chat" if require_tools else "tier-2-chat"
        return self._get_llm_from_pool(pool_id)

    def _get_llm_from_pool(self, pool_id: str):
        selected_ep = endpoint_pool_manager.select_best_endpoint(pool_id)
        if not selected_ep:
            raise ValueError(f"!!! [算力枯竭] 池 {pool_id} 及其降级链已全部失效。")
        
        main_llm = self._create_llm(selected_ep.id, selected_ep)
        pool = endpoint_pool_manager.pools.get(pool_id)
        fallback_objects = []
        if pool:
            for ep in pool.endpoints:
                if ep.id != selected_ep.id:
                    is_safe, _, _, _ = usage_tracker.check_limit(ep.id)
                    if is_safe:
                        f_llm = self._create_llm(ep.id, ep)
                        if f_llm: fallback_objects.append(f_llm)
        
        if main_llm is None:
            if fallback_objects:
                main_llm = fallback_objects.pop(0)
            else:
                raise ValueError(f"!!! [算力枯竭] 节点 {selected_ep.id} 及备选节点均未能成功创建 LLM。")

        if fallback_objects:
            return main_llm.with_fallbacks(fallback_objects), selected_ep.id
        return main_llm, selected_ep.id

    async def get_llm_by_role(self, role: str, retry_count: int = 0, config: Optional[Dict] = None):
        """[V66.0 Final] 异步高可用角色路由：集成自动探测与长效自愈"""
        model_override = None
        if config and isinstance(config, dict):
            model_override = config.get("configurable", {}).get("model_override")
        
        # 1. 初始寻址
        if model_override:
            llm, m_id = self.get_adaptive_llm(model_id=model_override)
        else:
            role_cfg = endpoint_pool_manager.roles.get(role)
            # [V134.2 优化] 支持角色绑定特定端点，实现测试环境的“确定性路径”
            if role_cfg and hasattr(role_cfg, "preferred_endpoint") and role_cfg.preferred_endpoint:
                logger.info(f"📍 [Role-Binding] 角色 {role} 强制绑定端点: {role_cfg.preferred_endpoint}")
                llm, m_id = self.get_adaptive_llm(model_id=role_cfg.preferred_endpoint)
            else:
                pool_id = role_cfg.pool if role_cfg else "tier-1-chat"
                llm, m_id = self._get_llm_from_pool(pool_id)

        # [V134.0 P3] Proactive Probe -> FastCheck (no network ping)
        if retry_count > 5:
            raise ValueError(f'All nodes for role {role} are banned.')

        import time as _time
        state = endpoint_pool_manager.states.get(m_id)
        # [V134.1 修复] 增加时间校验：如果 cooldown 已过，应允许其通过，否则会导致死循环寻址。
        if state and state.is_cooling and _time.time() < state.cooldown_until:
            logger.warning(f'[FastCheck] Node {m_id} still in cooldown, switching.')
            return await self.get_llm_by_role(role, retry_count + 1, config)

        logger.debug(f'[FastCheck] Node {m_id} is ready.')
        return llm, m_id

    def get_reranker(self, reranker_id: str = "gte-rerank"):
        cfg = self.providers.get(reranker_id)
        if not cfg:
            for k, v in self.providers.items():
                if "rerank" in k.lower():
                    cfg = v
                    reranker_id = k
                    break
        return Reranker(reranker_id, cfg) if cfg else None

    async def probe_all_endpoints(self):
        """[V201.0] 主动探活所有可用与处于熔断/冷却中的节点，实现智能探测自愈"""
        logger.info("🔍 [HealthCheck] 开始单次全量节点健康拨测...")
        
        # 收集所有独特的 endpoints
        endpoints_to_probe = {}
        for pool_id, pool in endpoint_pool_manager.pools.items():
            for ep in pool.endpoints:
                endpoints_to_probe[ep.id] = (ep, pool_id)
                
        healthy_count = 0
        recovered_count = 0
        failed_count = 0
        
        for ep_id, (ep, pool_id) in endpoints_to_probe.items():
            state = endpoint_pool_manager.states.get(ep_id)
            is_cooling = state and state.is_cooling
            is_blacklisted = ep_id in usage_tracker.blacklist_expiry
            
            # 如果不处于熔断/冷却状态，则可以认为健康
            if is_cooling or is_blacklisted:
                logger.info(f"⏳ [HealthCheck] 发现处于熔断或冷却的节点: {ep_id}，启动主动探活拨测...")
                
                # 尝试用非常便宜的 ping (max_tokens=1) 来探活
                success = await self._probe_single_endpoint(ep_id, ep)
                if success:
                    logger.success(f"💖 [HealthCheck] 节点 {ep_id} 拨测成功！立即激活恢复算力链路。")
                    # 解除冷却并清除黑名单
                    endpoint_pool_manager.record_success(ep_id)
                    recovered_count += 1
                else:
                    logger.warning(f"❌ [HealthCheck] 节点 {ep_id} 拨测依然失败，继续维持封禁。")
                    failed_count += 1
            else:
                healthy_count += 1
                
            # 同步状态至 Redis
            is_active = True
            if ep_id in usage_tracker.blacklist_expiry:
                is_active = False
            elif state and state.is_cooling:
                is_active = False
            redis_manager.record_node_health(ep_id, is_active)
            
        logger.info(f"📊 [HealthCheck] 拨测完成: 正常={healthy_count} | 恢复={recovered_count} | 封禁中={failed_count}")

    async def _probe_single_endpoint(self, ep_id: str, ep: Any) -> bool:
        """[V201.0] 对单个物理节点发送最廉价的 ping 请求以验证可用性"""
        provider = ep.provider
        api_key, base_url = self._resolve_credentials(ep)
        if not api_key:
            return False
            
        try:
            from langchain_core.messages import HumanMessage
            if provider == "google":
                # Google Gemini
                llm = ChatGoogleGenerativeAI(
                    model=ep.model_name,
                    api_key=api_key, 
                    google_api_key=api_key,
                    temperature=0.0,
                    timeout=10.0,
                    max_retries=0
                )
            elif provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                base_url = base_url or os.getenv("ANTHROPIC_BASE_URL", "http://103.236.76.197:11223/anthropic")
                llm = ChatAnthropic(
                    model_name=ep.model_name,
                    anthropic_api_key=api_key,
                    anthropic_api_url=base_url,
                    temperature=0.0,
                    timeout=10.0,
                    max_retries=0
                )
            else:
                default_headers = {}
                if provider == "dashscope":
                    default_headers["x-dashscope-sse"] = "enable"
                
                llm = ChatOpenAI(
                    model=ep.model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=0.0,
                    timeout=10.0,
                    max_retries=0,
                    default_headers=default_headers
                )
                
            await llm.ainvoke([HumanMessage(content="ping")], max_tokens=1)
            return True
        except Exception as e:
            logger.debug(f"拨测 {ep_id} 发生异常 (预期中): {e}")
            return False

    async def run_health_check(self):
        """[V90.0] 周期性健康检查: 校验端点池中每个 endpoint 的可用性。"""
        interval_seconds = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "300"))
        logger.info(f"[HealthCheck] 启动, interval={interval_seconds}s")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.probe_all_endpoints()
            except asyncio.CancelledError:
                logger.info("[HealthCheck] 收到取消信号, 优雅退出")
                break
            except Exception as e:
                logger.warning(f"[HealthCheck] 巡检异常: {e}")

# Backward-compatible alias, delegates to DI container
from app.core.container import LazyProxy

model_manager = LazyProxy("model_manager")
