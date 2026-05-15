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
from app.core.memory.base import MemoryItem, BaseStorage
from app.core.memory.embedding import embedding_engine

class VectorStorage(BaseStorage):
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.index_path = os.path.join(storage_dir, "vector.index")
        self.meta_path = os.path.join(storage_dir, "metadata.pkl")
        self.index = None
        self.items: List[MemoryItem] = []
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

    async def add(self, items: List[MemoryItem]):
        if not items: return
        
        texts = [str(item.content) for item in items]
        embeddings = np.array(embedding_engine.embed_documents(texts)).astype('float32')
        faiss.normalize_L2(embeddings)

        if self.index is None:
            dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
        
        self.index.add(embeddings)
        self.items.extend(items)
        self._save()

    async def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        if self.index is None or not self.items: return []
        
        query_vec = np.array([embedding_engine.embed_query(query)]).astype('float32')
        faiss.normalize_L2(query_vec)
        
        distances, indices = self.index.search(query_vec, limit)
        
        results = []
        for idx in indices[0]:
            if 0 <= idx < len(self.items):
                results.append(self.items[idx])
        return results

    def _save(self):
        try:
            faiss.write_index(self.index, self.index_path)
            with open(self.meta_path, "wb") as f:
                pickle.dump(self.items, f)
        except Exception as e:
            logger.error(f"保存向量索引失败: {e}")

    def clear(self):
        self.index = None
        self.items = []
        if os.path.exists(self.index_path): os.remove(self.index_path)
        if os.path.exists(self.meta_path): os.remove(self.meta_path)
