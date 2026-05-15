import os
import uuid
import json
import numpy as np
from datetime import datetime

# [V112.0] 物理稳定性加固：防止 Windows 下多重 OpenMP 运行时冲突导致的 forrtl 错误
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
from typing import List, Dict, Any, Optional, Sequence, Union
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from app.core.memory import memory_hub
from app.redis_client import redis_manager
# from sentence_transformers import SentenceTransformer, util - Lazy loaded below

# ============================================================
# 1. 核心架构：本地小模型嵌入引擎 (参考 hello-agents)
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
            logger.warning(f"⚠️ 本地模型加载失败（网络或路径问题），进入 Mock 模式: {e}")
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
    def __init__(self, storage_path: str, embeddings):
        self.storage_path = os.path.join(storage_path, "semantic")
        self._embeddings = embeddings
        os.makedirs(self.storage_path, exist_ok=True)

    def learn_experience(self, topic: str, content: Any, metadata: Dict[str, Any] = None):
        """将成功的审计经验固化为长期知识（增强类型容错）"""
        if isinstance(content, list):
            content = " ".join([str(i) for i in content])
        elif not isinstance(content, str):
            content = str(content)
            
        doc = Document(page_content=content, metadata={"topic": topic, **(metadata or {})})
        index_path = self.storage_path
        try:
            if os.path.exists(os.path.join(index_path, "index.faiss")):
                vector_store = FAISS.load_local(index_path, self._embeddings, allow_dangerous_deserialization=True)
                vector_store.add_documents([doc])
            else:
                vector_store = FAISS.from_documents([doc], self._embeddings)
            vector_store.save_local(index_path)
            logger.info(f"💡 [经验学习] 已成功沉淀审计经验: {topic}")
        except Exception as e:
            logger.error(f"经验学习失败: {e}")
        
        # [V140.2] 同时同步至 Redis L1 缓存，加速后续热点查询
        redis_manager.set_cache(f"exp:{topic}", content, expire_hours=72)

    def recall_expert_knowledge(self, query: str, k: int = 2, decay_rate: float = 0.05) -> List[Document]:
        """[V153.0] 专家经验召回：集成时间衰减因子 (Recency Bias)"""
        # 1. 优先尝试 Redis 快速路径
        cached = redis_manager.get_cache(f"exp_query:{query}")
        if cached:
            logger.success(f"⚡ [REDIS] 命中专家经验缓存: {query[:15]}...")
            return [Document(page_content=cached)]

        if not os.path.exists(os.path.join(self.storage_path, "index.faiss")): return []
        
        try:
            vector_store = FAISS.load_local(self.storage_path, self._embeddings, allow_dangerous_deserialization=True)
            # 使用带评分的搜索
            results_with_score = vector_store.similarity_search_with_score(query, k=k*2)
            
            # 2. 应用时间衰减 (Time Decay)
            # Score = Similarity * exp(-decay_rate * days_passed)
            # 注意：FAISS score 是 L2 距离，越小越相似，此处逻辑需适配
            scored_docs = []
            now = datetime.now()
            for doc, raw_score in results_with_score:
                # 转换 L2 为相似度近似值 (0~1)
                similarity = 1.0 / (1.0 + raw_score)
                
                # 计算时间衰减
                ts = doc.metadata.get("timestamp")
                if ts:
                    if isinstance(ts, str): ts = datetime.fromisoformat(ts)
                    days_passed = (now - ts).days
                    time_weight = np.exp(-decay_rate * days_passed)
                else:
                    time_weight = 0.8 # 无时间戳降权
                
                final_score = similarity * time_weight
                scored_docs.append((doc, final_score))
            
            # 按最终得分排序并取前 K
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            final_results = [d for d, s in scored_docs[:k]]

            if final_results:
                redis_manager.set_cache(f"exp_query:{query}", final_results[0].page_content)
            return final_results
            
        except Exception as e:
            logger.error(f"专家经验检索失败: {e}")
            return []

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
# 4. 动作压缩与语义缓存层 (Action Compression)
# ============================================================
class ActionCacheManager:
    def __init__(self, cache_file="data/action_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load()
        # [V159.0] 物理优化：构建精确匹配索引
        self.lookup = {item["question"].strip(): item for item in self.cache}
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            if not cognitive_memory_manager._local_engine:
                cognitive_memory_manager._init_components()
            self._engine = cognitive_memory_manager._local_engine
        return self._engine

    def _load(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        return []

    def save(self, question: str, sql: str, tasks: List[str] = None, methodology: str = ""):
        if not self.engine: return
        q_strip = question.strip()
        if q_strip in self.lookup: return
            
        emb = self.engine.embed_query(question)
        item = {
            "question": question, 
            "sql": sql, 
            "tasks": tasks or [], 
            "methodology": methodology,
            "embedding": emb,
            "timestamp": datetime.now().isoformat()
        }
        self.cache.append(item)
        self.lookup[q_strip] = item
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False)
        
        # [V140.2] 分布式同步
        redis_manager.set_cache(f"action_cache:{q_strip}", json.dumps(item), expire_hours=48)
        logger.success(f"💾 [Action Cache] 已固化审计动作链至分布式缓存: {question[:15]}...")

    def search(self, question: str, threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """[V159.0] 高性能语义搜索：返回完整的动作链载荷"""
        if not self.cache: return None
        
        q_strip = question.strip()
        # A. 内存字典匹配 (L0)
        if q_strip in self.lookup:
            logger.success(f"⚡ [Action Cache] 字典精确命中: {question[:15]}...")
            return self.lookup[q_strip]
        
        # B. Redis 分布式缓存匹配 (L1)
        cached_json = redis_manager.get_cache(f"action_cache:{q_strip}")
        if cached_json:
            logger.success(f"🚀 [REDIS] 动作链缓存命中: {question[:15]}...")
            return json.loads(cached_json)
                
        # 2. 语义相似度匹配
        if not self.engine: return None
        
        query_emb = np.array(self.engine.embed_query(question))
        query_norm = np.linalg.norm(query_emb)
        
        best_score = 0
        best_item = None
        
        for item in self.cache:
            if "embedding" in item:
                target_emb = np.array(item["embedding"])
                if len(target_emb) != len(query_emb): continue
                
                dot_product = np.dot(query_emb, target_emb)
                target_norm = np.linalg.norm(target_emb)
                score = dot_product / (query_norm * target_norm) if (query_norm * target_norm) != 0 else 0
                
                if score > best_score:
                    best_score = score
                    best_item = item
                
        if best_score >= threshold:
            logger.success(f"🔍 [Action Cache] 语义命中 (Score: {best_score:.2f}): {question[:15]}...")
            return best_item
        return None

sql_cache_manager = ActionCacheManager()
action_cache_manager = sql_cache_manager

# [V164.1] 挂载至统一记忆中枢
from app.core.memory import memory_hub
memory_hub.attach_component("episodic", action_cache_manager)
