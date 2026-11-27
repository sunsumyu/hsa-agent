import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from app.core.memory.action_cache import ActionCacheManager
from app.core.memory.experience import ExperienceManager


def test_action_cache_hit_count_and_stats(tmp_path):
    cache_file = tmp_path / "action_cache.json"
    mgr = ActionCacheManager(cache_file=str(cache_file))

    fake_redis = MagicMock()
    fake_redis.get_cache.return_value = None
    with patch("app.core.memory.action_cache.redis_manager", fake_redis):

        # 1. Miss before save
        assert mgr.search("未缓存的问题") is None

        # 2. Save entry (initial hit_count == 0)
        mgr.save(
            question="核查男性开具妇科用药",
            sql="SELECT * FROM fqz_fymx_test WHERE gend LIKE '1%'",
            tasks=["GENDER_CONFLICT"],
            fingerprint={"prompt_version": "2.0", "schema_hash": "hsa_v2_core"},
        )

        # 3. L0 exact hit + L0.5 canonical hit
        hit1 = mgr.search("核查男性开具妇科用药")
        assert hit1 is not None
        assert hit1["hit_count"] == 1

        hit2 = mgr.search("请帮我核查一下男性开具妇科用药！")
        assert hit2 is not None
        assert hit2["hit_count"] == 2

        stats = mgr.get_stats()
        assert stats["total_entries"] == 1
        assert stats["queries"] == 3
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hits_by_tier"]["L0"] == 1
        assert stats["hits_by_tier"]["L0.5"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3, rel=1e-3)
        assert stats["total_entry_hits"] == 2

        # 4. Evict increments eviction count
        mgr.evict("核查男性开具妇科用药")
        assert mgr.get_stats()["evictions"] == 1

        # 5. Persisted JSON reflects cleanup
        persisted = json.loads(cache_file.read_text(encoding="utf-8"))
        assert persisted == []


def test_experience_manager_hit_count_and_stats(tmp_path, monkeypatch):
    pool_file = tmp_path / "pool.json"
    index_dir = tmp_path / "faiss_index"
    monkeypatch.setattr("app.core.memory.experience.POOL_FILE", str(pool_file))
    monkeypatch.setattr("app.core.memory.experience.INDEX_PATH", str(index_dir))

    fake_adapter = MagicMock()
    fake_adapter.has_index.return_value = True
    fake_adapter.add_document.return_value = True

    mgr = ExperienceManager(vector_adapter=fake_adapter)
    mgr.save_audit_experience(["GENDER_CONFLICT"], "SELECT psn_no FROM fqz_fymx_test WHERE gend LIKE '1%'")

    fake_adapter.search.return_value = [
        Document(
            page_content="GENDER_CONFLICT",
            metadata={
                "intent": "GENDER_CONFLICT",
                "golden_sql": "SELECT psn_no FROM fqz_fymx_test WHERE gend LIKE '1%'",
            },
        )
    ]

    res = mgr.get_relevant_experience(["GENDER_CONFLICT"], k=1)
    assert "golden_sql" not in res  # formatted SQL block
    assert "SELECT psn_no FROM fqz_fymx_test" in res

    fake_adapter.search.return_value = []
    assert mgr.get_relevant_experience(["UNKNOWN_TASK"], k=1) == ""

    stats = mgr.get_stats()
    assert stats["total_entries"] == 1
    assert stats["queries"] == 2
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["total_entry_hits"] == 1

    saved_pool = json.loads(pool_file.read_text(encoding="utf-8"))
    assert saved_pool[0]["hit_count"] == 1
    assert saved_pool[0]["last_hit_at"]


def test_coder_prompt_assembler_injects_golden_experience(monkeypatch):
    monkeypatch.delenv("DISABLE_AUDIT_CACHE", raising=False)
    monkeypatch.delenv("IS_BENCHMARK_MODE", raising=False)

    from app.agents.coder_prompt_assembler import assemble_coder_prompt

    fake_golden = "### 参考历史成功案例 (Semantic Match):\n意图: GENDER_CONFLICT\nSQL: \n```sql\nSELECT 1\n```"
    with patch("app.core.memory.experience.experience_manager.get_relevant_experience", return_value=fake_golden) as mock_exp:
        payload = assemble_coder_prompt(
            state={
                "current_turn_query": "排查男性使用妇科药",
                "tasks": ["GENDER_CONFLICT"],
                "messages": [],
            }
        )
        mock_exp.assert_called_once()
        joined = "\n".join(str(getattr(m, "content", "")) for m in payload.prompt_messages)
        assert "参考历史成功案例" in joined
        assert "SELECT 1" in joined


def test_context_builder_gathers_golden_experience(monkeypatch):
    monkeypatch.delenv("DISABLE_AUDIT_CACHE", raising=False)
    monkeypatch.delenv("IS_BENCHMARK_MODE", raising=False)

    from app.core.context.context_builder import ContextBuilder

    cb = ContextBuilder()
    fake_golden = "### 参考历史成功案例 (Semantic Match):\n意图: GENDER_CONFLICT"
    with patch("app.core.memory.experience.experience_manager.get_relevant_experience", return_value=fake_golden), \
         patch("app.skills.federated.audit_note_store.audit_note_store.read_relevant_notes", return_value=[]):
        packets = cb._gather_all("排查男性使用妇科药", ["fqz_fymx_test"], [], {})
        types = [p.metadata.get("type") for p in packets]
        assert "golden_sql_experience" in types
        golden_pkt = next(p for p in packets if p.metadata.get("type") == "golden_sql_experience")
        assert "<golden_sql_example>" in golden_pkt.content
        assert "GENDER_CONFLICT" in golden_pkt.content


@pytest.mark.asyncio
async def test_memory_cache_stats_route():
    from app.api.routes.memory import get_cache_and_experience_stats

    resp = await get_cache_and_experience_stats()
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ok"] is True
    assert "action_cache" in payload["data"]
    assert "experience_pool" in payload["data"]
    assert "hit_rate" in payload["data"]["action_cache"]
    assert "hit_rate" in payload["data"]["experience_pool"]
