import typing
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.memory.base import MemoryItem
from app.core.memory.rag_utils import generate_hyde_document, generate_mqe_queries
from app.core.memory.storage.vector import VectorStorage
from app.data.raw_data_sanitizer import RawDataSanitizer


class _DummyEmbeddings:
    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_generate_mqe_queries_interpolates_n_and_handles_errors():
    mock_resp = SimpleNamespace(content="1. 分解住院\n2. 重复入院\n3. 短间隔再入院")
    with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, return_value=mock_resp) as mock_chat:
        queries = await generate_mqe_queries("分解住院排查", n=2)

    assert queries == ["分解住院", "重复入院"]
    system_prompt = mock_chat.await_args.kwargs["messages"][0][1]
    assert "2 个" in system_prompt
    assert "{n}" not in system_prompt

    with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        assert await generate_mqe_queries("分解住院排查", n=2) == []


@pytest.mark.asyncio
async def test_generate_hyde_document_handles_errors_without_name_error():
    with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        assert await generate_hyde_document("高额住院费用") is None


@pytest.mark.asyncio
async def test_vector_storage_round_trip_uses_json_not_pickle(tmp_path):
    vs = VectorStorage(storage_dir=str(tmp_path), embeddings=_DummyEmbeddings())
    item = MemoryItem(
        content="市一医院分解住院线索",
        memory_type="semantic",
        importance=0.9,
        metadata={"tenant_id": "t_json"},
    )
    await vs.add([item])

    assert (tmp_path / "metadata.json").exists()
    assert not (tmp_path / "metadata.pkl").exists()

    reloaded = VectorStorage(storage_dir=str(tmp_path), embeddings=_DummyEmbeddings())
    assert len(reloaded.items) == 1
    assert reloaded.items[0].content == "市一医院分解住院线索"
    assert reloaded.items[0].metadata["tenant_id"] == "t_json"


def test_raw_data_sanitizer_extract_scan_boundary_type_hints_resolve():
    hints = typing.get_type_hints(RawDataSanitizer.extract_scan_boundary)
    assert "return" in hints
