"""
app/memory/faiss_vector_adapter.py
==================================
[Matt Pocock Deep Module] FAISS 本地向量库持久化与检索适配器

核心职责：
1. 延迟加载 FAISS 避免模块导入期触发 langchain-community 弃用告警与启动开销
2. 封装 index.faiss 的物理目录探测、自动加载与新建
3. 封装 add_documents 与 similarity_search_with_score
4. 针对文件缺失与加载异常提供安全优雅的降级
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Tuple
from loguru import logger
from langchain_core.documents import Document


class FaissVectorAdapter:
    """FAISS 向量存储适配器深模块"""

    @staticmethod
    def _get_faiss_class():
        """延迟导入 FAISS 向量库，抑制顶层全局弃用告警"""
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                from langchain_community.vectorstores import FAISS
            return FAISS
        except Exception as e:
            logger.warning(f"[FaissVectorAdapter] FAISS 模块未安装或不可用: {e}")
            return None

    def has_index(self, storage_path: str) -> bool:
        """判断指定目录是否存在有效的 FAISS 索引文件"""
        return os.path.exists(os.path.join(storage_path, "index.faiss"))

    def get_raw_store(self, storage_path: str, embeddings: Any) -> Optional[Any]:
        """获取底层 FAISS 实例（延迟安全加载，仅向后兼容旧调用）"""
        faiss_cls = self._get_faiss_class()
        if not faiss_cls or embeddings is None or not self.has_index(storage_path):
            return None
        try:
            return faiss_cls.load_local(
                storage_path, embeddings, allow_dangerous_deserialization=True
            )
        except Exception as e:
            logger.error(f"[FaissVectorAdapter] 获取底层向量库失败 ({storage_path}): {e}")
            return None

    def add_documents(self, storage_path: str, embeddings: Any, docs: List[Document]) -> bool:
        """批量持久化保存文档到本地向量库"""
        if not docs:
            return True
        faiss_cls = self._get_faiss_class()
        if not faiss_cls or embeddings is None:
            return False

        os.makedirs(storage_path, exist_ok=True)

        try:
            if self.has_index(storage_path):
                vector_store = faiss_cls.load_local(
                    storage_path, embeddings, allow_dangerous_deserialization=True
                )
                vector_store.add_documents(docs)
            else:
                vector_store = faiss_cls.from_documents(docs, embeddings)
            vector_store.save_local(storage_path)
            return True
        except Exception as e:
            logger.error(f"[FaissVectorAdapter] 写入向量存储失败 ({storage_path}): {e}")
            return False

    def add_document(self, storage_path: str, embeddings: Any, doc: Document) -> bool:
        """持久化保存单条文档到本地向量库"""
        return self.add_documents(storage_path, embeddings, [doc])

    def search_with_score(
        self,
        storage_path: str,
        embeddings: Any,
        query: str,
        k: int = 4,
    ) -> List[Tuple[Document, float]]:
        """执行带 L2 距离的相似度向量检索"""
        faiss_cls = self._get_faiss_class()
        index_file = os.path.join(storage_path, "index.faiss")

        if not faiss_cls or not os.path.exists(index_file) or embeddings is None:
            return []

        try:
            vector_store = faiss_cls.load_local(
                storage_path, embeddings, allow_dangerous_deserialization=True
            )
            return vector_store.similarity_search_with_score(query, k=k)
        except Exception as e:
            logger.error(f"[FaissVectorAdapter] 检索向量存储失败 ({storage_path}): {e}")
            return []

    def search(
        self,
        storage_path: str,
        embeddings: Any,
        query: str,
        k: int = 2,
    ) -> List[Document]:
        """简易无评分检索"""
        scored = self.search_with_score(storage_path, embeddings, query, k=k)
        return [doc for doc, _ in scored]


# 全局默认适配器实例
faiss_vector_adapter = FaissVectorAdapter()
