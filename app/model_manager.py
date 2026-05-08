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
from sentence_transformers import SentenceTransformer, util
import torch

load_dotenv()

class EnrichedChatOpenAI(ChatOpenAI):
    """[V40.0] 财务加固型 ChatModel：物理拦截响应并补全缺失的 Token 用量数据"""
    
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self._enrich_result(result, messages)
            return result
        except Exception as e:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            endpoint_pool_manager.record_failure(m_id, str(e))
            raise e

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self._enrich_result(result, messages)
            return result
        except Exception as e:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            endpoint_pool_manager.record_failure(m_id, str(e))
            raise e

    def _enrich_result(self, result, messages):
        """物理注入逻辑封装"""
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
            endpoint_pool_manager.record_failure(m_id, str(e))
            raise e

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            return result
        except Exception as e:
            m_id = getattr(self, 'model_name', getattr(self, 'model', 'unknown'))
            endpoint_pool_manager.record_failure(m_id, str(e))
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
        try:
            # 优先加载本地多语言小模型，处理中文审计更精准
            self.local_embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("✅ [本地模型] 已加载嵌入式语义路由引擎 (MiniLM-L12)")
        except Exception as e:
            logger.warning(f"本地语义模型加载失败: {e}，将回退至通用模式")
            self.local_embedder = None
        
    def classify_complexity_locally(self, text: str) -> str:
        return "MEDIUM"
        
    def _load_config(self) -> Dict[str, ModelConfig]:
        try:
            if not os.path.exists(self.config_path): return {}
            with open(self.config_path, 'r', encoding='utf-8') as f:
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
                return EnrichedChatOpenAI(
                    model=model_name,
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                    temperature=temperature,
                    timeout=60.0,
                    streaming=True,
                    default_headers=default_headers
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
        
        logger.info(f">>> [池化寻址] 池: {pool_id} | 选中: {selected_ep.id} | 备选数: {len(fallback_objects)}")
        
        if fallback_objects:
            return main_llm.with_fallbacks(fallback_objects), selected_ep.id
        return main_llm, selected_ep.id

    def get_llm_by_role(self, role: str, retry_count: int = 0, config: Optional[Dict] = None):
        model_override = None
        if config and isinstance(config, dict):
            model_override = config.get("configurable", {}).get("model_override")
        if model_override:
            return self.get_adaptive_llm(model_id=model_override)

        role_cfg = endpoint_pool_manager.roles.get(role)
        if not role_cfg: return self.get_adaptive_llm()
        return self._get_llm_from_pool(role_cfg.pool)

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
        import asyncio
        from langchain_core.messages import HumanMessage
        model_ids = list(self.providers.keys())
        async def probe_single(m_id):
            cfg = self.providers[m_id]
            try:
                llm = self._create_llm(m_id, cfg, bypass_limit=True)
                if not llm: return m_id, False
                await llm.ainvoke([HumanMessage(content="1")])
                usage_tracker.record_success(m_id)
                return m_id, True
            except:
                return m_id, False
        results = await asyncio.gather(*[probe_single(m) for m in model_ids])
        return {"healthy_count": len([r for r in results if r[1]]), "total": len(model_ids)}

model_manager = ModelManager()
