import os
import json
import logging
from loguru import logger
from typing import Dict, Optional, List, Any
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
import requests
from app.usage_tracker import usage_tracker
from app.endpoint_pool_manager import endpoint_pool_manager
from app.schemas import ModelConfig, EndpointConfig, RoleConfigV2
from app.observability import get_callbacks
from dotenv import load_dotenv
# load_dotenv() - Moved below
import requests
from app.usage_tracker import usage_tracker
from app.endpoint_pool_manager import endpoint_pool_manager
from app.schemas import ModelConfig, EndpointConfig, RoleConfigV2
from app.observability import get_callbacks
from dotenv import load_dotenv

load_dotenv()

class EnrichedChatOpenAI(ChatOpenAI):
    """[V40.0] 财务加固型 ChatModel：物理拦截响应并补全缺失的 Token 用量数据"""
    endpoint_id: str = "unknown" # [V77.0] 明确定义字段，防止 Pydantic 校验失败
    
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self._enrich_result(result, messages)
            return result
        except Exception as e:
            # [V75.0] 统一物理 ID 追踪：使用 endpoint_id 而不是模糊的 model_name
            m_id = getattr(self, 'endpoint_id', getattr(self, 'model_name', 'unknown'))
            err_msg = str(e)
            
            fatal_quota_sigs = ["SetLimitExceeded", "quota_exceeded", "balance", "余额不足", "限额已达到"]
            is_fatal = any(sig in err_msg for sig in fatal_quota_sigs)
            
            if not is_fatal and ("429" in err_msg or "limit" in err_msg.lower()):
                import asyncio
                retry_count = getattr(self, '_rate_limit_retry', 0)
                if retry_count < 2:
                    self._rate_limit_retry = retry_count + 1
                    wait_time = (retry_count + 1) * 2 
                    logger.warning(f"⏳ [RateLimit-Retry] 节点 {m_id} 触发限速，等待 {wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
                    return await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            
            logger.error(f"⛔ [FATAL_QUOTA] 物理节点 {m_id} 彻底封死，触发切流: {err_msg}")
            endpoint_pool_manager.record_failure(m_id, err_msg)
            raise e

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self._enrich_result(result, messages)
            return result
        except Exception as e:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            err_msg = str(e)
            
            fatal_quota_sigs = ["SetLimitExceeded", "quota_exceeded", "balance", "余额不足", "限额已达到"]
            is_fatal = any(sig in err_msg for sig in fatal_quota_sigs)
            
            if not is_fatal and ("429" in err_msg or "limit" in err_msg.lower()):
                import time
                retry_count = getattr(self, '_rate_limit_retry_sync', 0)
                if retry_count < 2:
                    self._rate_limit_retry_sync = retry_count + 1
                    wait_time = (retry_count + 1) * 2
                    logger.warning(f"⏳ [RateLimit-Retry-Sync] 节点 {m_id} 触发限速，等待 {wait_time}s 后重试...")
                    time.sleep(wait_time)
                    return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

            logger.error(f"⛔ [FATAL_QUOTA_SYNC] 节点 {m_id} 额度枯竭，触发切流: {err_msg}")
            endpoint_pool_manager.record_failure(m_id, err_msg)
            raise e

    def _enrich_result(self, result, messages):
        # [V72.0] Anti-Chat Guard: 物理过滤闲聊废话
        content = str(result.generations[0].message.content)
        chatty_keywords = ["你好", "很高兴为您服务", "我是一个大语言模型", "作为一个AI", "有什么可以帮您", "抱歉"]
        if any(kw in content for kw in chatty_keywords) and len(content) < 300:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            logger.warning(f"🚫 [ANTI_CHAT] 节点 {m_id} 输出了闲聊废话，强行判定为失败并切流。")
            endpoint_pool_manager.record_failure(m_id, "Detected conversational chatty response.")
            raise ValueError(f"Chatty response detected from {m_id}")

        prompt_text = "".join([str(m.content) for m in messages if hasattr(m, "content")])
        
        for gen in result.generations:
            msg = gen.message
            actual_model = msg.response_metadata.get("model_name", "unknown")
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            
            # 如果没有 metadata 或 total_tokens 为 0，执行物理估算
            if not getattr(msg, "usage_metadata", None) or msg.usage_metadata.get("total_tokens", 0) == 0:
                in_t = usage_tracker._estimate_tokens(prompt_text)
                out_t = usage_tracker._estimate_tokens(str(msg.content))
                
                msg.usage_metadata = {
                    "input_tokens": in_t,
                    "output_tokens": out_t,
                    "total_tokens": in_t + out_t
                }

class EnrichedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """[V40.1] 为 Google Gemini 提供故障感知的增强类"""
    
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            return result
        except Exception as e:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            err_msg = str(e)
            
            if "429" in err_msg or "limit" in err_msg.lower():
                import asyncio
                retry_count = getattr(self, '_rate_limit_retry', 0)
                if retry_count < 2:
                    self._rate_limit_retry = retry_count + 1
                    wait_time = (retry_count + 1) * 2
                    logger.warning(f"⏳ [RateLimit-Retry-Google] 节点 {m_id} 触发限速，等待 {wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
                    return await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

            endpoint_pool_manager.record_failure(m_id, err_msg)
            raise e

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            return result
        except Exception as e:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            err_msg = str(e)
            
            if "429" in err_msg or "limit" in err_msg.lower():
                import time
                retry_count = getattr(self, '_rate_limit_retry_sync', 0)
                if retry_count < 2:
                    self._rate_limit_retry_sync = retry_count + 1
                    wait_time = (retry_count + 1) * 2
                    logger.warning(f"⏳ [RateLimit-Retry-Sync-Google] 节点 {m_id} 触发限速，等待 {wait_time}s 后重试...")
                    time.sleep(wait_time)
                    return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

            endpoint_pool_manager.record_failure(m_id, err_msg)
            raise e

class Reranker:
    """[V44.0] 物理重排序算子：支持火山引擎 Rerank 接口"""
    def __init__(self, name: str, cfg: ModelConfig):
        self.name = name
        self.cfg = cfg
        self.api_key = os.getenv(cfg.api_key_env)
        self.base_url = os.getenv(cfg.base_url_env, "https://ark.cn-beijing.volces.com/api/v3")

    def rerank(self, query: str, documents: List[str], top_n: int = 3) -> List[Dict]:
        if not documents: return []
        
        if self.cfg.provider == "volcengine":
            url = f"{self.base_url}/rerank"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"model": self.cfg.model_name, "query": query, "documents": documents, "top_n": top_n}
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    usage_tracker.record_success(self.name)
                    return resp.json().get("results", [])
            except Exception as e:
                logger.error(f"Volc Rerank 异常: {e}")
                usage_tracker.record_failure(self.name, str(e))

        elif self.cfg.provider == "dashscope":
            url = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-DashScope-ApiKey": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.cfg.model_name,
                "input": {"query": query, "documents": documents},
                "parameters": {"top_n": top_n}
            }
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    usage_tracker.record_success(self.name)
                    return resp.json().get("output", {}).get("results", [])
            except Exception as e:
                logger.error(f"DashScope Rerank 异常: {e}")
                usage_tracker.record_failure(self.name, str(e))
        
        return [{"index": i, "relevance_score": 1.0 - (i * 0.1)} for i in range(min(len(documents), top_n))]

class ModelManager:
    def __init__(self, config_path="app/llm_providers.json"):
        self.config_path = config_path
        self.providers: Dict[str, ModelConfig] = self._load_config()
        self._local_embedder = None
        
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

    def classify_complexity_locally(self, text: str) -> str:
        # 暂时保持简单逻辑，如需扩展则调用 self.local_embedder
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
        api_key = os.getenv(cfg.api_key_env)
        base_url = os.getenv(cfg.base_url_env) if hasattr(cfg, 'base_url_env') and cfg.base_url_env else None
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
                    streaming=True
                )
            else:
                llm = EnrichedChatOpenAI(
                    model=model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    default_headers=default_headers,
                    endpoint_id=name # [V77.0] 在初始化时传入，符合 Pydantic 规范
                )
                return llm
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
        
        logger.info(f">>> [池化寻址] 池: {pool_id} | 选中: {selected_ep.id} | 备选数: {len(fallback_objects)}")
        
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
            pool_id = role_cfg.pool if role_cfg else "tier-1-chat"
            llm, m_id = self._get_llm_from_pool(pool_id)

        # 2. 物理嗅探 (Pre-flight Probing)
        if retry_count > 5:
            raise ValueError(f"🚨 [算力绝望] 角色 {role} 对应的所有备选节点均已进入封禁期。")

        from langchain_core.messages import HumanMessage
        try:
            pool = endpoint_pool_manager.pools.get(endpoint_pool_manager.roles[role].pool if role in endpoint_pool_manager.roles else "tier-1-chat")
            ep = next((e for e in pool.endpoints if e.id == m_id), None)
            
            if ep:
                # [V76.2] 物理前置校验：如果节点已在黑名单，严禁发起主动嗅探，防止产生噪音
                state = endpoint_pool_manager.states.get(m_id)
                if state and state.is_cooling:
                    logger.warning(f"🚷 [Proactive-Probe] 节点 {m_id} 仍在冷冻期，直接跳过寻址。")
                    return await self.get_llm_by_role(role, retry_count + 1, config)

                logger.info(f"🔍 [Proactive-Probe] 正在验证角色 {role} 的首选节点: {m_id}...")
                probe_llm = self._create_llm(m_id, ep)
                # 注入 ID 以确保探测失败也能精准熔断
                probe_llm.endpoint_id = m_id 
                await probe_llm.ainvoke([HumanMessage(content="1")], config={"timeout": 3.0})
                logger.info(f"✨ [Proactive-Probe] 节点 {m_id} 存活确认")
        except Exception as e:
            err_msg = str(e)
            if any(sig in err_msg.lower() for sig in ["429", "quota", "limit", "rate", "体验模式", "chatty"]):
                logger.warning(f"⛔ [Proactive-Probe] 节点 {m_id} 验证失败（配额/闲聊拦截），触发全局熔断。")
                endpoint_pool_manager.record_failure(m_id, err_msg)
                return await self.get_llm_by_role(role, retry_count + 1, config)
            else:
                logger.debug(f"ℹ️ [Proactive-Probe] 节点 {m_id} 探测异常 (非配额问题，暂不熔断): {err_msg}")
        
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

    async def run_health_check(self):
        """[V44.0] 基础健康检查占位"""
        pass

model_manager = ModelManager()
