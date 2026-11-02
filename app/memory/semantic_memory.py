import os
import uuid
import json
import numpy as np
from datetime import datetime

# [V112.0] 物理稳定性加固：防止 Windows 下多重 OpenMP 运行时冲突导致的 forrtl 错误
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
from typing import List, Dict, Any, Optional, Sequence, Union, Callable
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from app.core.memory import memory_hub
from app.infra.redis_client import redis_manager
from app.memory.decay_scoring import compute_decayed_score
from app.memory.vector_adapter_factory import get_vector_adapter
# from sentence_transformers import SentenceTransformer, util - Lazy loaded below

# ============================================================
# 1. 核心架构：本地小模型嵌入引擎
# ============================================================

class LocalEmbeddingEngine(Embeddings):
    """[V47.7] 本地轻量级向量引擎：实现零成本、离线记忆检索"""
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            # 优先加载多语言小模型，处理中文医保政策更精准
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"✅ [延迟加载] 本地记忆引擎加载成功: {self.model_name}")
        except Exception as e:
            logger.warning(f"⚠️ 本地模型加载失败（网络或路径问题），已切换至旁路直通模式（跳过向量计算）: {e}")
            self.model = None
            # [V81.0] 强制不报错，防止阻塞主流程
            return

    def embed_query(self, text: str) -> List[float]:
        if not self.model: return [0.0] * 384
        return self.model.encode(text).tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not self.model: return [[0.0] * 384] * len(texts)
        return self.model.encode(texts).tolist()

# ============================================================
# 2. 数据结构定义
# ============================================================

class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    memory_type: str  # working, episodic, semantic
    timestamp: datetime = Field(default_factory=datetime.now)
    importance: float = 0.5
    metadata: Dict[str, Any] = {}

class MemoryConfig(BaseModel):
    storage_path: str = "data/memory_v2"
    working_capacity: int = 15
    importance_threshold: float = 0.7
    local_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

# ============================================================
# 3. 记忆分层实现
# ============================================================

class WorkingMemory:
    """[工作记忆]：保持最近 15 轮审计交互，类似 RAM"""
    def __init__(self, capacity: int = 15):
        self.capacity = capacity
        self.buffer: List[MemoryItem] = []

    def add(self, content: Any, metadata: Dict[str, Any] = None):
        # 兼容列表输入 (Gemma 4 等模型)
        if isinstance(content, list):
            content = " ".join([str(i) for i in content])
        elif not isinstance(content, str):
            content = str(content)
            
        item = MemoryItem(content=content, memory_type="working", metadata=metadata or {})
        self.buffer.append(item)
        if len(self.buffer) > self.capacity: self.buffer.pop(0)
        return item

class SemanticMemory:
    """[语义记忆]：跨会话的审计经验库（核心策略、SQL 模板）"""
    def __init__(self, storage_path: str, embeddings, adapter=None):
        self.storage_path = os.path.join(storage_path, "semantic")
        self._embeddings = embeddings
        self._adapter = adapter or get_vector_adapter()
        os.makedirs(self.storage_path, exist_ok=True)

    def learn_experience(self, topic: str, content: Any, metadata: Dict[str, Any] = None):
        """将成功的审计经验固化为长期知识（增强类型容错）"""
        if isinstance(content, list):
            content = " ".join([str(i) for i in content])
        elif not isinstance(content, str):
            content = str(content)

        doc = Document(page_content=content, metadata={"topic": topic, **(metadata or {})})
        success = self._adapter.add_document(self.storage_path, self._embeddings, doc)
        if success:
            logger.info(f"💡 [经验学习] 已成功沉淀审计经验: {topic}")
        else:
            logger.warning(f"💡 [经验学习] 写入向量存储已跳过或异常: {topic}")

        # [V140.2] 同时同步至 Redis L1 缓存，加速后续热点查询
        redis_manager.set_cache(f"exp:{topic}", content, expire_hours=72)

    def recall_expert_knowledge(self, query: str, k: int = 2, decay_rate: float = 0.05) -> List[Document]:
        """[V153.0] 专家经验召回：集成时间衰减因子 (Recency Bias)"""
        # 1. 优先尝试 Redis 快速路径
        cached = redis_manager.get_cache(f"exp_query:{query}")
        if cached:
            logger.success(f"⚡ [REDIS] 命中专家经验缓存: {query[:15]}...")
            return [Document(page_content=cached)]

        # 2. 向量检索与时间衰减评分
        results_with_score = self._adapter.search_with_score(
            self.storage_path, self._embeddings, query, k=k * 2
        )
        if not results_with_score:
            return []

        now = datetime.now()
        scored_docs = []
        for doc, raw_score in results_with_score:
            ts = doc.metadata.get("timestamp")
            final_score = compute_decayed_score(
                raw_l2_score=raw_score,
                timestamp=ts,
                decay_rate=decay_rate,
                now=now,
            )
            scored_docs.append((doc, final_score))

        # 按最终得分降序并取 Top K
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        final_results = [d for d, _ in scored_docs[:k]]

        if final_results:
            redis_manager.set_cache(f"exp_query:{query}", final_results[0].page_content)
        return final_results

class CognitiveMemoryManager:
    """[V47.7] 本地化认知记忆中心"""
    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()
        self._local_engine = None
        self.working = WorkingMemory(capacity=self.config.working_capacity)
        self.semantic: Optional[SemanticMemory] = None

    def _init_components(self):
        if self._local_engine is None:
            self._local_engine = LocalEmbeddingEngine(model_name=self.config.local_model)
        if self.semantic is None:
            self.semantic = SemanticMemory(self.config.storage_path, self._local_engine)

    def add_audit_event(self, content: str, importance: float = 0.5, topic: str = "general"):
        """记录审计事件，并评估是否存入长期经验库"""
        self._init_components()
        self.working.add(content, {"topic": topic})
        
        # 语义增强：如果发现 SQL 成功执行或违规金额巨大，自动存入语义记忆
        if "SELECT" in content and "成功" in content:
            importance += 0.4
        
        if importance >= self.config.importance_threshold:
            self.semantic.learn_experience(topic, content)

    def add_message(self, session_id: str, message: Any, importance: float = 0.5):
        """[兼容性接口] 将消息对象适配为审计事件记录"""
        content = getattr(message, "content", str(message))
        self.add_audit_event(content, importance=importance, topic=f"session_{session_id}")

    def recall_context(self, session_id: str, query: str) -> str:
        """从工作记忆和长期语义库中联合召回"""
        self._init_components()
        results = ["【工作记忆 (近期)】"]
        recent = self.working.buffer
        results.extend([f"- {item.content[:100]}..." for item in recent[-3:]])
        
        expert_knowledge = self.semantic.recall_expert_knowledge(query)
        if expert_knowledge:
            results.append("\n【审计经验召回 (跨会话)】")
            results.extend([f"  (经验) {doc.page_content[:200]}" for doc in expert_knowledge])
            
# 全局单例
cognitive_memory_manager = CognitiveMemoryManager()
semantic_memory_manager = cognitive_memory_manager

# ============================================================
# 4. 动作压缩与语义缓存层 (委托至 action_cache 深模块)
# ============================================================
from app.memory.action_cache import (
    ActionCacheManager,
    action_cache_manager,
    sql_cache_manager,
)

# [V164.1] 挂载至统一记忆中枢
from app.core.memory import memory_hub
memory_hub.attach_component("episodic", action_cache_manager)
