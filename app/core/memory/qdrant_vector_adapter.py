"""
app/core/memory/qdrant_vector_adapter.py
===================================
[Matt Pocock Deep Module] Qdrant Cloud 向量存储与检索适配器

核心职责：
1. 封装 QdrantClient 连接与单例管理，支持 URL 与 API Key 鉴权。
2. 规范化本地路径为合法的 Qdrant 集合名称（HNSW 索引，Cosine 距离）。
3. 对齐 FaissVectorAdapter 的统一接口（add_documents, search_with_score 等）。
4. 异常安全保障：网络或服务端异常时安全记录错误并返回优雅降级状态。
"""

from __future__ import annotations

import os
import uuid
import re
from typing import Any, List, Optional, Tuple
from loguru import logger
from langchain_core.documents import Document

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    QdrantClient = None
    models = None


def path_to_collection_name(storage_path: str) -> str:
    """将本地存储路径转换为合法的 Qdrant 集合名称"""
    cleaned = storage_path.replace("\\", "/").strip("/")
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", cleaned)
    return f"argus_{cleaned}"


class QdrantVectorAdapter:
    """Qdrant 向量存储适配器"""

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 15,
        hnsw_m: int = 32,
        hnsw_ef_construct: int = 256,
        search_ef: int = 128,
    ):
        self.url = url or os.getenv("QDRANT_URL")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.timeout = timeout
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct
        self.search_ef = search_ef
        self._client: Optional[Any] = None

    def _get_client(self) -> Optional[Any]:
        if not QDRANT_AVAILABLE:
            logger.warning("[QdrantVectorAdapter] qdrant-client 未安装")
            return None
        url = self.url or os.getenv("QDRANT_URL")
        api_key = self.api_key or os.getenv("QDRANT_API_KEY")
        if self._client is None:
            if not url:
                logger.warning("[QdrantVectorAdapter] QDRANT_URL 未配置")
                return None
            try:
                self._client = QdrantClient(
                    url=url,
                    api_key=api_key,
                    timeout=self.timeout,
                )
            except Exception as e:
                logger.error(f"[QdrantVectorAdapter] 初始化连接失败: {e}")
                return None
        return self._client

    def has_index(self, storage_path: str) -> bool:
        client = self._get_client()
        if not client:
            return False
        col_name = path_to_collection_name(storage_path)
        try:
            collections = client.get_collections().collections
            return any(c.name == col_name for c in collections)
        except Exception as e:
            logger.warning(f"[QdrantVectorAdapter] 检查集合存在失败 ({col_name}): {e}")
            return False

    def _ensure_collection(self, client: Any, col_name: str, vector_size: int) -> bool:
        try:
            collections = client.get_collections().collections
            if not any(c.name == col_name for c in collections):
                client.create_collection(
                    collection_name=col_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                    hnsw_config=models.HnswConfigDiff(
                        m=self.hnsw_m,
                        ef_construct=self.hnsw_ef_construct,
                    ),
                )
                logger.info(f"✅ [QdrantVectorAdapter] 创建云端集合成功: {col_name}")
            return True
        except Exception as e:
            logger.error(f"[QdrantVectorAdapter] 创建集合失败 ({col_name}): {e}")
            return False

    def add_documents(
        self, storage_path: str, embeddings: Any, docs: List[Document]
    ) -> bool:
        if not docs:
            return True
        client = self._get_client()
        if not client or embeddings is None:
            return False

        col_name = path_to_collection_name(storage_path)
        try:
            texts = [doc.page_content for doc in docs]
            vectors = embeddings.embed_documents(texts)
            if not vectors:
                return False
            vector_size = len(vectors[0])

            if not self._ensure_collection(client, col_name, vector_size):
                return False

            points = []
            for i, (doc, vec) in enumerate(zip(docs, vectors)):
                point_id = doc.metadata.get("id") or str(uuid.uuid4())
                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=vec,
                        payload={
                            "page_content": doc.page_content,
                            "metadata": doc.metadata,
                        },
                    )
                )

            client.upsert(collection_name=col_name, points=points)
            logger.info(f"✅ [QdrantVectorAdapter] 成功写入 {len(points)} 条文档到集合 {col_name}")
            return True
        except Exception as e:
            logger.error(f"[QdrantVectorAdapter] 写入文档异常 ({col_name}): {e}")
            return False

    def add_document(self, storage_path: str, embeddings: Any, doc: Document) -> bool:
        return self.add_documents(storage_path, embeddings, [doc])

    def search_with_score(
        self,
        storage_path: str,
        embeddings: Any,
        query: str,
        k: int = 4,
    ) -> List[Tuple[Document, float]]:
        client = self._get_client()
        if not client or embeddings is None:
            return []

        col_name = path_to_collection_name(storage_path)
        try:
            query_vector = embeddings.embed_query(query)
            response = client.query_points(
                collection_name=col_name,
                query=query_vector,
                limit=k,
                search_params=models.SearchParams(
                    hnsw_ef=self.search_ef,
                    exact=False,
                ),
            )
            results: List[Tuple[Document, float]] = []
            for point in getattr(response, "points", []):
                payload = point.payload or {}
                content = payload.get("page_content", "")
                meta = payload.get("metadata", {})
                score = float(point.score)
                results.append((Document(page_content=content, metadata=meta), score))
            return results
        except Exception as e:
            logger.error(f"[QdrantVectorAdapter] 检索向量异常 ({col_name}): {e}")
            return []

    def search(
        self,
        storage_path: str,
        embeddings: Any,
        query: str,
        k: int = 4,
    ) -> List[Document]:
        scored = self.search_with_score(storage_path, embeddings, query, k=k)
        return [doc for doc, _ in scored]

    def delete_documents(self, storage_path: str, ids: List[str]) -> bool:
        client = self._get_client()
        if not client or not ids:
            return False
        col_name = path_to_collection_name(storage_path)
        try:
            client.delete(
                collection_name=col_name,
                points_selector=models.PointIdsList(points=ids),
            )
            return True
        except Exception as e:
            logger.error(f"[QdrantVectorAdapter] 删除文档异常 ({col_name}): {e}")
            return False


qdrant_vector_adapter = QdrantVectorAdapter()
