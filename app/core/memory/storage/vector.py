"""
app/core/memory/storage/vector.py
=================================
[V177.2] 向量存储后端 (FAISS Vector Storage)
"""

import os
import faiss
import numpy as np
import pickle
from typing import List, Optional
from loguru import logger
from app.core.memory.base import MemoryItem, BaseStorage, StorageStats
from app.core.memory.embedding import embedding_engine

class VectorStorage(BaseStorage):
    def __init__(self, storage_dir: str, embeddings=None):
        self.storage_dir = storage_dir
        self.index_path = os.path.join(storage_dir, "vector.index")
        self.meta_path = os.path.join(storage_dir, "metadata.pkl")
        self.index = None
        self.items: List[MemoryItem] = []
        self._embeddings = embeddings or embedding_engine
        self.hits = 0
        self.misses = 0
        os.makedirs(storage_dir, exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.meta_path, "rb") as f:
                    self.items = pickle.load(f)
                logger.info(f"✅ [VectorStorage] 已从磁盘加载索引 (条目数: {len(self.items)})")
            except Exception as e:
                logger.error(f"加载向量索引失败: {e}")

    async def add(self, items: List[MemoryItem], embeddings_engine=None):
        if not items: return
        
        # 允许传入特定的 Embedder（如 CLIP），否则使用实例默认 Embedder
        engine = embeddings_engine or self._embeddings
        
        texts = [str(item.content) for item in items]
        embeddings = np.array(engine.embed_documents(texts)).astype('float32')
        faiss.normalize_L2(embeddings)

        if self.index is None:
            dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
        
        self.index.add(embeddings)
        self.items.extend(items)
        self._save()

    async def search(self, query: Optional[str] = None, limit: int = 5, tenant_id: str = "default", query_vector: Optional[List[float]] = None) -> List[MemoryItem]:
        if self.index is None or not self.items: return []
        
        # 1. 优先使用预计算的向量（支持多模态），否则进行实时文本编码
        if query_vector:
            q_vec = np.array([query_vector]).astype('float32')
        elif query:
            q_vec = np.array([self._embeddings.embed_query(query)]).astype('float32')
        else:
            return []
            
        faiss.normalize_L2(q_vec)
        
        # 为了多租户过滤，检索更多候选项 (如 5x limit)
        internal_limit = limit * 5
        distances, indices = self.index.search(q_vec, internal_limit)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(self.items):
                item = self.items[idx].model_copy() # 深拷贝防止污染原始条目
                if item.metadata.get("tenant_id", "default") == tenant_id:
                    item.score = float(dist) # FAISS normalize_L2 + IndexFlatIP 返回的是余弦相似度
                    results.append(item)
                    if len(results) >= limit: break
        
        if results:
            self.hits += 1
        else:
            self.misses += 1
            
        return results

    def _save(self):
        try:
            faiss.write_index(self.index, self.index_path)
            with open(self.meta_path, "wb") as f:
                pickle.dump(self.items, f)
        except Exception as e:
            logger.error(f"保存向量索引失败: {e}")

    async def forget(self, threshold: float) -> int:
        """根据重要性阈值清理向量记忆并重建索引"""
        original_count = len(self.items)
        # 过滤掉低于阈值的项
        new_items = [item for item in self.items if item.importance >= threshold]
        
        if len(new_items) == original_count:
            return 0
            
        self.items = new_items
        if not self.items:
            self.index = None
        else:
            # 重建索引
            texts = [str(item.content) for item in self.items]
            embeddings = np.array(self._embeddings.embed_documents(texts)).astype('float32')
            faiss.normalize_L2(embeddings)
            
            dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
            self.index.add(embeddings)
            
        self._save()
        return original_count - len(self.items)

    def get_name(self) -> str:
        return "FAISS-Vector-Storage"

    def get_stats(self) -> StorageStats:
        size = 0
        if os.path.exists(self.index_path): size += os.path.getsize(self.index_path)
        if os.path.exists(self.meta_path): size += os.path.getsize(self.meta_path)
        
        return StorageStats(
            total_items=len(self.items),
            storage_size_bytes=size,
            hits=self.hits,
            misses=self.misses
        )

    def clear(self):
        self.index = None
        self.items = []
        if os.path.exists(self.index_path): os.remove(self.index_path)
        if os.path.exists(self.meta_path): os.remove(self.meta_path)
