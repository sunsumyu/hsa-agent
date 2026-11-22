"""
app/core/memory/vector_adapter_factory.py
====================================
[Matt Pocock Deep Module] 向量存储适配器工厂与容灾路由

职责：
1. 根据环境变量 VECTOR_STORE_BACKEND 返回对应的向量适配器。
2. 当配置为 qdrant 但连接失败或未就绪时，自动记录告警并回退至 faiss_vector_adapter。
3. 提供统一的 get_vector_adapter() 接缝。
"""

import os
from typing import Any, Optional
from loguru import logger

from app.core.memory.faiss_vector_adapter import faiss_vector_adapter, FaissVectorAdapter
from app.core.memory.qdrant_vector_adapter import qdrant_vector_adapter, QdrantVectorAdapter


def get_vector_adapter(backend: Optional[str] = None) -> Any:
    """获取当前处于激活状态的向量存储适配器（带自动容灾回退）"""
    target_backend = (backend or os.getenv("VECTOR_STORE_BACKEND", "faiss")).lower().strip()

    if target_backend == "qdrant":
        # 探测 Qdrant 客户端健康状态
        try:
            client = qdrant_vector_adapter._get_client()
            if client is not None:
                # 简单握手检查连通性
                client.get_collections()
                return qdrant_vector_adapter
            else:
                logger.warning("⚠️ [VectorAdapterFactory] Qdrant 客户端初始化失败，自动降级至 FAISS")
                return faiss_vector_adapter
        except Exception as e:
            logger.warning(f"⚠️ [VectorAdapterFactory] Qdrant 云端探测失败 ({e})，自动容灾降级至 FAISS")
            return faiss_vector_adapter

    return faiss_vector_adapter
