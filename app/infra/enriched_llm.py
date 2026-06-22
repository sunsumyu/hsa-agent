"""
app/infra/enriched_llm.py
=========================
[Phase 3.3] Enriched LLM wrappers and reranker.

Extracted from model_manager.py. These classes add fault-awareness (anti-chat
guard, rate-limit retry, token estimation) to ChatOpenAI and ChatGoogleGenerativeAI.
"""

import asyncio
import time
from loguru import logger
from typing import Dict, List, Any
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from app.infra.usage_tracker import usage_tracker
from app.infra.endpoint_pool_manager import endpoint_pool_manager
from app.core.schemas import ModelConfig


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
            # [V178.9] 自动探测平台标签
            platform_tag = "未知平台"
            endpoint_cfg = endpoint_pool_manager.get_endpoint_config(m_id)
            if endpoint_cfg:
                platform_tag = "火山引擎" if endpoint_cfg.platform == "volcengine" else "DeepSeek官网" if endpoint_cfg.platform == "official" else "阿里百炼"
            
            err_msg = str(e)
            disp_name = endpoint_pool_manager.get_endpoint_display_name(m_id)
            logger.error(f"⛔ [{platform_tag}] 物理节点 {disp_name} 异常: {str(err_msg)[:100]}...")
            
            fatal_quota_sigs = ["SetLimitExceeded", "quota_exceeded", "balance", "余额不足", "限额已达到"]
            is_fatal = any(sig in err_msg for sig in fatal_quota_sigs)
            
            # [V90.6] 400 InvalidParameter (消息顺序等) 是请求级别 bug，不应熔断节点
            _is_request_bug = "InvalidParameter" in err_msg or "Invalid messages" in err_msg
            if _is_request_bug:
                logger.warning(f"⚠️ [REQUEST_BUG] 节点 {m_id} 返回 400 参数错误 (不熔断): {err_msg[:200]}")
                raise e
            
            if not is_fatal and ("429" in err_msg or "limit" in err_msg.lower()):
                import asyncio
                retry_count = getattr(self, '_rate_limit_retry', 0)
                if retry_count < 2:
                    self._rate_limit_retry = retry_count + 1
                    wait_time = (retry_count + 1) * 2 
                    logger.warning(f"⏳ [RateLimit-Retry] 节点 {m_id} 触发限速，等待 {wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
                    return await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            
            # [V178.9] 执行自动切流
            endpoint_pool_manager.record_failure(m_id, err_msg)
            raise e

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self._enrich_result(result, messages)
            return result
        except Exception as e:
            m_id = getattr(self, 'endpoint_id', getattr(self, 'model_name', 'unknown'))
            err_msg = str(e)
            
            # [V178.9] 平台标签探测
            platform_tag = "未知平台"
            endpoint_cfg = endpoint_pool_manager.get_endpoint_config(m_id)
            if endpoint_cfg:
                platform_tag = "火山引擎" if endpoint_cfg.platform == "volcengine" else "DeepSeek官网" if endpoint_cfg.platform == "official" else "阿里百炼"
            
            fatal_quota_sigs = ["SetLimitExceeded", "quota_exceeded", "balance", "余额不足", "限额已达到"]
            is_fatal = any(sig in err_msg for sig in fatal_quota_sigs)
            
            # [V90.6] 400 InvalidParameter 不熔断
            _is_request_bug = "InvalidParameter" in err_msg or "Invalid messages" in err_msg
            if _is_request_bug:
                logger.warning(f"⚠️ [REQUEST_BUG_SYNC] 节点 {m_id} 返回 400 参数错误 (不熔断): {err_msg[:200]}")
                raise e
            
            if not is_fatal and ("429" in err_msg or "limit" in err_msg.lower()):
                import time
                retry_count = getattr(self, '_rate_limit_retry_sync', 0)
                if retry_count < 2:
                    self._rate_limit_retry_sync = retry_count + 1
                    wait_time = (retry_count + 1) * 2
                    disp_name = endpoint_pool_manager.get_endpoint_display_name(m_id)
                    logger.warning(f"⏳ [RateLimit-Retry-Sync] 节点 {disp_name} 触发限速，等待 {wait_time}s 后重试...")
                    time.sleep(wait_time)
                    return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

            disp_name = endpoint_pool_manager.get_endpoint_display_name(m_id)
            logger.error(f"⛔ [{platform_tag}] 节点 {disp_name} 额度枯竭，触发切流: {str(err_msg)[:100]}...")
            endpoint_pool_manager.record_failure(m_id, err_msg)
            raise e

    def _enrich_result(self, result, messages):
        # [V72.0] Anti-Chat Guard: 物理过滤闲聊废话
        # [V90.6] Probe 豁免：探活消息 ("ping") 的回复必然是闲聊，不应触发熔断
        _is_probe = (
            len(messages) == 1
            and hasattr(messages[0], "content")
            and str(messages[0].content).strip().lower() in ("ping", "1", "hi", "test")
        )
        content = str(result.generations[0].message.content)
        chatty_keywords = ["你好", "很高兴为您服务", "我是一个大语言模型", "作为一个AI", "有什么可以帮您", "抱歉"]
        if not _is_probe and any(kw in content for kw in chatty_keywords) and len(content) < 300:
            m_id = getattr(self, 'endpoint_id', getattr(self, 'model_name', getattr(self, 'model', 'unknown')))
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
    endpoint_id: str = "unknown"
    
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            return result
        except Exception as e:
            m_id = getattr(self, 'endpoint_id', getattr(self, 'model_name', getattr(self, 'model', 'unknown')))
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
            m_id = getattr(self, 'endpoint_id', getattr(self, 'model_name', getattr(self, 'model', 'unknown')))
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
