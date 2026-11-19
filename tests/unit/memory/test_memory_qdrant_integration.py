import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from app.memory.experience import ExperienceManager
from app.memory.semantic_memory import SemanticMemory

def test_experience_manager_uses_vector_adapter_factory():
    mock_adapter = MagicMock()
    mock_adapter.search.return_value = [
        Document(
            page_content="SELECT * FROM test",
            metadata={"golden_sql": "SELECT * FROM test", "intent": "查男性妇科"}
        )
    ]

    manager = ExperienceManager(vector_adapter=mock_adapter)
    # 模拟 pool 文件检查不触发同步
    manager._sync_index_from_pool_if_needed = MagicMock(return_value=True)

    exp = manager.get_relevant_experience(["查男性妇科"], k=1)
    assert "SELECT * FROM test" in exp

def test_semantic_memory_store_uses_vector_adapter_factory():
    mock_adapter = MagicMock()
    mock_adapter.search_with_score.return_value = [
        (Document(page_content="避坑规则: 禁用伪排除", metadata={"timestamp": "2026-11-01T12:00:00"}), 0.95)
    ]

    store = SemanticMemory(
        storage_path="data/test_memory",
        embeddings=MagicMock(),
        adapter=mock_adapter
    )
    items = store.recall_expert_knowledge("伪排除", k=1)
    assert len(items) == 1
    assert items[0].page_content == "避坑规则: 禁用伪排除"
