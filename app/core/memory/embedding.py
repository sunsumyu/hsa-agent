"""
app/core/memory/embedding.py
============================
[V177.1] 统一嵌入服务 (Unified Embedding Service)
"""

import os
from typing import List
from loguru import logger
from langchain_core.embeddings import Embeddings

class LocalEmbeddingEngine(Embeddings):
    """本地轻量级向量引擎，实现零成本、离线记忆检索"""
    
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LocalEmbeddingEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        if self._initialized: return
        self.model_name = model_name
        self.model = None
        self._load_attempted = False
        self._initialized = True

    def _ensure_model(self):
        if self._load_attempted:
            return
        self._load_attempted = True
        if os.getenv("DISABLE_LOCAL_EMBEDDING", "").lower() in ("true", "1") or os.getenv("HF_HUB_OFFLINE") == "1":
            logger.info("⚡ [MemoryHub] 检测到离线模式，自动旁路跳过本地大模型加载。")
            self.model = None
            return
        # [V4.5.4] 延迟加载：避免在模块导入时同步加载大模型导致主进程与测试死锁
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"✅ [MemoryHub] 本地嵌入模型加载成功: {self.model_name}")
        except Exception as e:
            logger.warning(f"⚠️ 嵌入模型加载失败，进入 Mock 模式: {e}")
            self.model = None

    def embed_query(self, text: str) -> List[float]:
        self._ensure_model()
        if not self.model: return [0.0] * 384
        return self.model.encode(text).tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self._ensure_model()
        if not self.model: return [[0.0] * 384] * len(texts)
        return self.model.encode(texts).tolist()

# 单例导出
embedding_engine = LocalEmbeddingEngine()
