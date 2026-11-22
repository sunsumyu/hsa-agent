"""
tests/unit/core/test_memory_p0_fixes.py
=======================================
验证记忆中枢 P0 修复项：
1. MemoryHub.graph_storage 初始化与后台语义入库闭环
2. WorkingMemory 与 MemoryHub.recall 多租户隔离
3. EpisodicMemory 接入 MemoryHub.recall 主召回流
4. SemanticMemory 动态 HyDE 触发门控
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.memory.base import MemoryItem
from app.core.memory.manager import memory_hub
from app.core.memory.storage.graph import GraphStorage
from app.core.memory.types.semantic import SemanticMemory
from app.core.memory.types.working import WorkingMemory


def test_memory_hub_graph_storage_initialized():
    """验证 MemoryHub._init_hub 正确初始化了 graph_storage"""
    assert hasattr(memory_hub, "graph_storage")
    assert isinstance(memory_hub.graph_storage, GraphStorage)


def test_working_memory_tenant_isolation():
    """验证 WorkingMemory 在多租户场景下 L0/L1 读写与检索相互隔离"""
    mock_redis = MagicMock()
    mock_client = MagicMock()
    mock_redis.client = mock_client

    wm = WorkingMemory(redis_client=mock_redis)
    wm.store("k1", "租户A的机密规则", ttl=60, tenant_id="tenant_a")
    wm.store("k1", "租户B的机密规则", ttl=60, tenant_id="tenant_b")

    # 校验 L0 隔离
    assert wm.recall("k1", tenant_id="tenant_a") == "租户A的机密规则"
    assert wm.recall("k1", tenant_id="tenant_b") == "租户B的机密规则"
    assert wm.recall("k1", tenant_id="default") is None

    # 校验 Redis Key 前缀隔离
    called_keys = [call.args[0] for call in mock_client.setex.call_args_list]
    assert "hsa:working:tenant_a:k1" in called_keys
    assert "hsa:working:tenant_b:k1" in called_keys

    # 校验 search 隔离
    hits_a = wm.search("机密规则", limit=5, tenant_id="tenant_a")
    assert len(hits_a) == 1
    assert hits_a[0].content == "租户A的机密规则"
    assert hits_a[0].metadata["tenant_id"] == "tenant_a"


@pytest.mark.asyncio
async def test_memory_hub_recall_routes_tenant_storage_and_includes_episodic():
    """验证 MemoryHub.recall 按租户分片路由并并发召回情景记忆"""
    tenant_vector = MagicMock()
    tenant_relational = MagicMock()
    tenant_storage = {"vector": tenant_vector, "relational": tenant_relational}

    sem_item = MemoryItem(content="语义规则", memory_type="semantic", importance=0.8)
    epi_item = MemoryItem(
        content={"question": "历史审计", "methodology": "SQL校验"},
        memory_type="episodic",
        importance=0.9,
    )

    with patch.object(memory_hub, "_get_tenant_storage", return_value=tenant_storage), \
         patch.object(memory_hub.semantic, "recall", new=AsyncMock(return_value=[sem_item])) as mock_sem, \
         patch.object(memory_hub.perceptual, "recall", new=AsyncMock(return_value=[])) as mock_perc, \
         patch.object(memory_hub.episodic, "recall_experience", new=AsyncMock(return_value=[epi_item])) as mock_epi:
        results = await memory_hub.recall("医保违规规则", limit=5, tenant_id="tenant_xyz")

    mock_sem.assert_awaited_once_with("医保违规规则", limit=15, tenant_id="tenant_xyz", storage=tenant_vector)
    mock_perc.assert_awaited_once_with("医保违规规则", limit=15, tenant_id="tenant_xyz")
    mock_epi.assert_awaited_once_with("医保违规规则", limit=15, tenant_id="tenant_xyz", storage=tenant_relational)
    assert len(results) == 2
    assert {r.memory_type for r in results} == {"semantic", "episodic"}


def test_semantic_memory_dynamic_hyde_gating():
    """验证 SemanticMemory._should_use_hyde 动态门控逻辑"""
    assert SemanticMemory._should_use_hyde("oprn_fee", None) is False
    assert SemanticMemory._should_use_hyde("医保", None) is False
    assert SemanticMemory._should_use_hyde("请排查市一医院今年门诊重组人促红素违规情况", None) is True
    assert SemanticMemory._should_use_hyde("oprn_fee", True) is True
    assert SemanticMemory._should_use_hyde("请排查市一医院今年门诊重组人促红素违规情况", False) is False


@pytest.mark.asyncio
async def test_vector_storage_upsert_with_conflict_resolution(tmp_path):
    """验证长期向量库写入时能通过 MemoryConflictArbiter 覆写同实体同属性的旧冲突记忆"""
    from app.core.memory.conflict_arbiter import memory_conflict_arbiter
    from app.core.memory.storage.vector import VectorStorage

    class DummyEmbeddings:
        def embed_documents(self, texts):
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text):
            return [1.0, 0.0, 0.0, 0.0]

    vs = VectorStorage(storage_dir=str(tmp_path), embeddings=DummyEmbeddings())
    old_item = MemoryItem(
        content="市一医院存在违规刷单嫌疑",
        memory_type="semantic",
        importance=0.8,
        metadata={"tenant_id": "t1"},
    )
    new_item = MemoryItem(
        content="市一医院核查正常无违规",
        memory_type="semantic",
        importance=0.9,
        metadata={"tenant_id": "t1"},
    )

    removed_first = await vs.upsert_with_conflict_resolution(old_item, arbiter=memory_conflict_arbiter)
    assert removed_first == 0
    assert len(vs.items) == 1

    removed_second = await vs.upsert_with_conflict_resolution(new_item, arbiter=memory_conflict_arbiter)
    assert removed_second == 1
    assert len(vs.items) == 1
    assert vs.items[0].content == "市一医院核查正常无违规"


def test_health_inspector_collects_storage_hit_rate_and_counts():
    """验证 MemoryHealthInspector 能聚合语义/情景库条目数与检索命中率"""
    from app.core.memory.base import StorageStats
    from app.core.memory.health_inspector import MemoryHealthInspector

    inspector = MemoryHealthInspector()
    mock_vec = MagicMock()
    mock_vec.get_stats.return_value = StorageStats(
        total_items=12, storage_size_bytes=4096, hits=3, misses=1
    )
    mock_rel = MagicMock()
    mock_rel.get_stats.return_value = StorageStats(
        total_items=8, storage_size_bytes=2048, hits=5, misses=0
    )

    stats = inspector.inspect(
        working_cache={},
        perceptual_component=None,
        storage_pool={},
        vector_storage=mock_vec,
        relational_storage=mock_rel,
    )
    l1 = stats["layers"]["l1_semantic"]
    l2 = stats["layers"]["l2_episodic"]
    assert l1["total_items"] == 12
    assert l1["hit_rate"] == 0.75
    assert l2["total_items"] == 8

    summary = inspector.format_summary(stats)
    assert "12条(命中率75%)" in summary
    assert "8条" in summary


def test_memory_hub_periodic_gc_start_stop():
    """验证 MemoryHub 周期性 GC 定时器可正常启停"""
    memory_hub.start_periodic_gc(interval_seconds=3600)
    assert memory_hub._gc_running is True
    assert memory_hub._gc_timer is not None
    memory_hub.stop_periodic_gc()
    assert memory_hub._gc_running is False
    assert memory_hub._gc_timer is None


def test_legacy_cognitive_memory_manager_recall_context_returns_string():
    """验证旧版 CognitiveMemoryManager.recall_context 正常返回并桥接 MemoryHub 工作记忆"""
    from app.core.memory.semantic_memory import CognitiveMemoryManager

    mgr = CognitiveMemoryManager()
    mgr.working.add("旧版工作记忆线索")
    mgr.semantic = MagicMock()
    mgr.semantic.recall_expert_knowledge.return_value = []

    memory_hub.store_working("bridge_test", "医保基金监管重点线索", ttl=60)
    ctx = mgr.recall_context("s1", "医保基金")
    assert isinstance(ctx, str)
    assert "旧版工作记忆线索" in ctx
    assert "医保基金监管重点线索" in ctx


@pytest.mark.asyncio
async def test_app_lifespan_starts_and_stops_memory_gc():
    """验证 FastAPI lifespan 在启动与关闭时自动启停 MemoryHub 周期性 GC"""
    from contextlib import asynccontextmanager
    from app.main import lifespan, app

    @asynccontextmanager
    async def dummy_checkpointer():
        yield MagicMock()

    with patch("app.main.register_services"), \
         patch("app.main.create_checkpointer", side_effect=dummy_checkpointer), \
         patch("app.main.init_observability"), \
         patch("app.core.observability.shutdown_observability"), \
         patch("app.main.usage_tracker.should_run_startup_probe", return_value=False), \
         patch("app.core.container.ServiceProvider.dispose_all"), \
         patch.object(memory_hub, "start_periodic_gc") as mock_start, \
         patch.object(memory_hub, "stop_periodic_gc") as mock_stop:
        async with lifespan(app):
            mock_start.assert_called_once_with(interval_seconds=3600)
            mock_stop.assert_not_called()
        mock_stop.assert_called_once()
