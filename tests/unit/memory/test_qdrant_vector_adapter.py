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
