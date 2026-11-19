# Qdrant Cloud 向量存储双引擎接入实施计划 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Argus-Agent 接入 Qdrant Cloud 向量数据库作为生产级云端向量存储后端，并实现与本地 FAISS 的双引擎无缝切换与优雅降级。

**Architecture:** 采用 Matt Pocock 深模块架构与适配器模式，通过 `QdrantVectorAdapter` 封装 Qdrant Client 集合管理与 HNSW 索引调优，由 `VectorAdapterFactory` 统一读取环境变量并在网络故障或未配置时自动回退至 `FaissVectorAdapter`。

**Tech Stack:** Python 3.11+, `qdrant-client>=1.10.0`, `langchain-core`, `faiss-cpu`, `pytest`.

## Global Constraints

- 遵循单一职责与窄接口原则，适配器对外必须满足 `has_index`, `add_documents`, `search_with_score`, `delete_documents` 统一方法签名。
- 绝不允许由于云端 Qdrant 网络连接失败、超时或密钥错误导致智能体主业务流程崩溃，必须自动优雅回退至本地 FAISS。
- 保证离线环境与单元测试的 100% 独立性与向后兼容性。

---

### Task 1: Qdrant 适配器核心深模块 (`QdrantVectorAdapter`)

**Files:**
- Create: `app/memory/qdrant_vector_adapter.py`
- Test: `tests/unit/memory/test_qdrant_vector_adapter.py`

**Interfaces:**
- Consumes: `qdrant_client`, `langchain_core.documents.Document`, `langchain_core.embeddings.Embeddings`
- Produces: `QdrantVectorAdapter` 类与 `qdrant_vector_adapter` 单例实例，提供方法：
  - `path_to_collection_name(storage_path: str) -> str`
  - `has_index(storage_path: str) -> bool`
  - `add_documents(storage_path: str, embeddings: Any, docs: List[Document]) -> bool`
  - `add_document(storage_path: str, embeddings: Any, doc: Document) -> bool`
  - `search_with_score(storage_path: str, embeddings: Any, query: str, k: int = 4) -> List[Tuple[Document, float]]`
  - `delete_documents(storage_path: str, ids: List[str]) -> bool`

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/unit/memory/test_qdrant_vector_adapter.py
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from app.memory.qdrant_vector_adapter import (
    QdrantVectorAdapter,
    path_to_collection_name,
)

def test_path_to_collection_name():
    assert path_to_collection_name("data/memory_v2") == "argus_data_memory_v2"
    assert path_to_collection_name("store\\experiences\\") == "argus_store_experiences"
    assert path_to_collection_name("simple") == "argus_simple"

@patch("app.memory.qdrant_vector_adapter.QdrantClient")
def test_qdrant_vector_adapter_add_and_search(mock_qdrant_client_cls):
    mock_client = MagicMock()
    mock_qdrant_client_cls.return_value = mock_client
    
    # 模拟集合不存在时创建集合
    mock_client.get_collections.return_value.collections = []

    adapter = QdrantVectorAdapter(url="https://mock.qdrant.io", api_key="test-key")
    
    # 模拟 embedding
    mock_embeddings = MagicMock()
    mock_embeddings.embed_documents.return_value = [[0.1] * 384, [0.2] * 384]
    mock_embeddings.embed_query.return_value = [0.1] * 384

    docs = [
        Document(page_content="规则1: 诊疗伴随检查", metadata={"rule_id": "R01"}),
        Document(page_content="规则2: 药品限男性使用", metadata={"rule_id": "R02"}),
    ]

    ok = adapter.add_documents("data/test_memory", mock_embeddings, docs)
    assert ok is True
    assert mock_client.create_collection.called
    assert mock_client.upsert.called

    # 模拟检索返回
    mock_scored_point = MagicMock()
    mock_scored_point.score = 0.88
    mock_scored_point.payload = {
        "page_content": "规则1: 诊疗伴随检查",
        "metadata": {"rule_id": "R01"}
    }
    mock_client.query_points.return_value.points = [mock_scored_point]

    results = adapter.search_with_score("data/test_memory", mock_embeddings, "诊疗检查", k=2)
    assert len(results) == 1
    doc, score = results[0]
    assert doc.page_content == "规则1: 诊疗伴随检查"
    assert doc.metadata["rule_id"] == "R01"
    assert score == pytest.approx(0.88)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/memory/test_qdrant_vector_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.memory.qdrant_vector_adapter'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/memory/qdrant_vector_adapter.py
"""
app/memory/qdrant_vector_adapter.py
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
        if self._client is None:
            if not self.url:
                logger.warning("[QdrantVectorAdapter] QDRANT_URL 未配置")
                return None
            try:
                self._client = QdrantClient(
                    url=self.url,
                    api_key=self.api_key,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/memory/test_qdrant_vector_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/memory/qdrant_vector_adapter.py tests/unit/memory/test_qdrant_vector_adapter.py
git commit -m "feat(memory): implement QdrantVectorAdapter with HNSW indexing and collection mapping"
```

---

### Task 2: 向量适配器工厂与优雅降级 (`VectorAdapterFactory`)

**Files:**
- Create: `app/memory/vector_adapter_factory.py`
- Test: `tests/unit/memory/test_vector_adapter_factory.py`

**Interfaces:**
- Consumes: `app.memory.faiss_vector_adapter.faiss_vector_adapter`, `app.memory.qdrant_vector_adapter.qdrant_vector_adapter`
- Produces: `get_vector_adapter(backend: Optional[str] = None)` 函数，返回统一向量适配器实例。

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/unit/memory/test_vector_adapter_factory.py
import pytest
from unittest.mock import patch, MagicMock

from app.memory.vector_adapter_factory import get_vector_adapter
from app.memory.faiss_vector_adapter import FaissVectorAdapter
from app.memory.qdrant_vector_adapter import QdrantVectorAdapter

def test_factory_returns_faiss_by_default(monkeypatch):
    monkeypatch.delenv("VECTOR_STORE_BACKEND", raising=False)
    adapter = get_vector_adapter()
    assert isinstance(adapter, FaissVectorAdapter)

def test_factory_returns_faiss_when_explicitly_configured(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "faiss")
    adapter = get_vector_adapter()
    assert isinstance(adapter, FaissVectorAdapter)

def test_factory_returns_qdrant_when_healthy(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://mock.qdrant.io")
    monkeypatch.setenv("QDRANT_API_KEY", "mock-key")

    with patch("app.memory.qdrant_vector_adapter.QdrantClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value.collections = []

        adapter = get_vector_adapter()
        assert isinstance(adapter, QdrantVectorAdapter)

def test_factory_falls_back_to_faiss_when_qdrant_unreachable(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://broken.qdrant.io")

    with patch("app.memory.qdrant_vector_adapter.QdrantClient", side_effect=Exception("Connection refused")):
        adapter = get_vector_adapter()
        # 降级到 FAISS，保证系统永不挂死
        assert isinstance(adapter, FaissVectorAdapter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/memory/test_vector_adapter_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.memory.vector_adapter_factory'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/memory/vector_adapter_factory.py
"""
app/memory/vector_adapter_factory.py
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

from app.memory.faiss_vector_adapter import faiss_vector_adapter, FaissVectorAdapter
from app.memory.qdrant_vector_adapter import qdrant_vector_adapter, QdrantVectorAdapter


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/memory/test_vector_adapter_factory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/memory/vector_adapter_factory.py tests/unit/memory/test_vector_adapter_factory.py
git commit -m "feat(memory): implement VectorAdapterFactory with graceful fallback to FAISS"
```

---

### Task 3: 上层调用端改造 (`SemanticMemory` & `ExperienceManager`)

**Files:**
- Modify: `app/memory/semantic_memory.py:18`
- Modify: `app/memory/experience.py:24-30`
- Test: `tests/unit/memory/test_memory_qdrant_integration.py`

**Interfaces:**
- Consumes: `app.memory.vector_adapter_factory.get_vector_adapter`
- Produces: 长期记忆与经验库具备无感适配 Qdrant / FAISS 双引擎的能力。

- [ ] **Step 1: Write integration unit test**

```python
# tests/unit/memory/test_memory_qdrant_integration.py
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from app.memory.experience import ExperienceManager
from app.memory.semantic_memory import SemanticMemoryStore, MemoryConfig

def test_experience_manager_uses_vector_adapter_factory(monkeypatch):
    mock_adapter = MagicMock()
    mock_adapter.search.return_value = [
        Document(page_content="SELECT * FROM test", metadata={"task": "查男性妇科"})
    ]

    with patch("app.memory.experience.get_vector_adapter", return_value=mock_adapter):
        manager = ExperienceManager()
        # 强制替换内部 adapter 验证对接
        manager._adapter = mock_adapter
        results = manager.search_similar_experiences("查男性妇科", k=1)
        assert len(results) == 1
        assert results[0].page_content == "SELECT * FROM test"

def test_semantic_memory_store_uses_vector_adapter_factory(monkeypatch):
    mock_adapter = MagicMock()
    mock_adapter.search_with_score.return_value = [
        (Document(page_content="避坑规则: 禁用伪排除"), 0.95)
    ]

    with patch("app.memory.semantic_memory.get_vector_adapter", return_value=mock_adapter):
        store = SemanticMemoryStore(
            storage_path="data/test_memory",
            embeddings=MagicMock(),
            adapter=mock_adapter
        )
        items = store.search("伪排除", k=1)
        assert len(items) == 1
        assert items[0].content == "避坑规则: 禁用伪排除"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/memory/test_memory_qdrant_integration.py -v`
Expected: FAIL (parameters or import not matching)

- [ ] **Step 3: Modify `experience.py` and `semantic_memory.py`**

在 `app/memory/experience.py` 中：
```python
from app.memory.vector_adapter_factory import get_vector_adapter

class ExperienceManager:
    def __init__(self, adapter=None):
        self._adapter = adapter or get_vector_adapter()
```

在 `app/memory/semantic_memory.py` 中：
```python
from app.memory.vector_adapter_factory import get_vector_adapter

class SemanticMemoryStore:
    def __init__(self, storage_path: str, embeddings, adapter=None):
        self.storage_path = storage_path
        self._embeddings = embeddings
        self._adapter = adapter or get_vector_adapter()
```
将原先直接调用 `faiss_vector_adapter` 的地方统一改为 `self._adapter`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/memory/test_memory_qdrant_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/memory/experience.py app/memory/semantic_memory.py tests/unit/memory/test_memory_qdrant_integration.py
git commit -m "refactor(memory): wire ExperienceManager and SemanticMemoryStore to VectorAdapterFactory"
```

---

### Task 4: Qdrant Cloud 真实云端端到端联调测试

**Files:**
- Create: `tests/eval/test_qdrant_cloud_live_e2e.py`

**Interfaces:**
- Consumes: 本地真实 `.env` 中的 `QDRANT_URL` 与 `QDRANT_API_KEY`
- Produces: 验证真实插入、真实 HNSW 检索、真实删除与集合清理完整闭环。

- [ ] **Step 1: Write the live e2e integration test**

```python
# tests/eval/test_qdrant_cloud_live_e2e.py
import os
import pytest
from dotenv import load_dotenv
load_dotenv()

from langchain_core.documents import Document
from app.memory.qdrant_vector_adapter import qdrant_vector_adapter, path_to_collection_name
from app.core.memory.embedding import embedding_engine

@pytest.mark.skipif(
    not os.getenv("QDRANT_URL") or not os.getenv("QDRANT_API_KEY"),
    reason="Qdrant Cloud 凭据未配置，跳过在线集成测试"
)
def test_qdrant_cloud_live_roundtrip():
    test_storage = "tests/live_audit_test"
    col_name = path_to_collection_name(test_storage)

    client = qdrant_vector_adapter._get_client()
    assert client is not None, "Qdrant 客户端未连接"

    # 清理遗留
    try:
        client.delete_collection(col_name)
    except Exception:
        pass

    try:
        docs = [
            Document(
                page_content="医保避坑指南: 男性使用妇科诊疗项目必须在 WHERE 子句中正向约束 gend LIKE '1%'",
                metadata={"archetype": "exclusion", "rule": "R_MALE_GYN"}
            ),
            Document(
                page_content="医保结算审核: 门诊慢特病药品跨机构高频超量购药需在参保人维度做 GROUP BY 统计",
                metadata={"archetype": "drug_resale", "rule": "R_DRUG_FREQ"}
            ),
        ]

        # 1. 写入真实 Qdrant Cloud
        ok = qdrant_vector_adapter.add_documents(test_storage, embedding_engine, docs)
        assert ok is True

        # 2. 真实云端检索
        results = qdrant_vector_adapter.search_with_score(
            test_storage,
            embedding_engine,
            query="男性做妇科检查违规怎么查",
            k=2
        )
        assert len(results) >= 1
        top_doc, score = results[0]
        assert "男性使用妇科诊疗项目" in top_doc.page_content
        assert top_doc.metadata.get("archetype") == "exclusion"
        assert score > 0.4

    finally:
        # 3. 清理云端测试集合
        try:
            client.delete_collection(col_name)
        except Exception:
            pass
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/eval/test_qdrant_cloud_live_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/eval/test_qdrant_cloud_live_e2e.py
git commit -m "test(memory): add live e2e integration test for Qdrant Cloud"
```
