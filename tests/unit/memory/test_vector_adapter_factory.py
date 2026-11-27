import pytest
from unittest.mock import patch, MagicMock

from app.core.memory.vector_adapter_factory import get_vector_adapter
from app.core.memory.faiss_vector_adapter import FaissVectorAdapter
from app.core.memory.qdrant_vector_adapter import QdrantVectorAdapter, qdrant_vector_adapter

@pytest.fixture(autouse=True)
def reset_qdrant_singleton():
    qdrant_vector_adapter._client = None
    yield
    qdrant_vector_adapter._client = None

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

    with patch("app.core.memory.qdrant_vector_adapter.QdrantClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value.collections = []

        adapter = get_vector_adapter()
        assert isinstance(adapter, QdrantVectorAdapter)

def test_factory_falls_back_to_faiss_when_qdrant_unreachable(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://broken.qdrant.io")

    with patch("app.core.memory.qdrant_vector_adapter.QdrantClient", side_effect=Exception("Connection refused")):
        adapter = get_vector_adapter()
        # 降级到 FAISS，保证系统永不挂死
        assert isinstance(adapter, FaissVectorAdapter)
