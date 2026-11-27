"""
tests/unit/core/test_memory_eviction_and_health_red.py
=====================================================
[Matt Pocock Deep Module Red Test] 记忆中枢健康巡检与三维淘汰 GC 算法独立解耦架构审计
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.core.memory.eviction_engine import MemoryEvictionEngine
from app.core.memory.health_inspector import MemoryHealthInspector


@pytest.mark.asyncio
async def test_eviction_engine_parameter_validation():
    """验证淘汰引擎参数边界严格校验"""
    engine = MemoryEvictionEngine()

    # 1. 非法策略
    with pytest.raises(ValueError, match="不支持的遗忘淘汰策略"):
        await engine.evict(
            relational_storage=MagicMock(),
            vector_storage=MagicMock(),
            working_cache={},
            strategy="invalid_strat"
        )

    # 2. 阈值超出 [0.0, 1.0]
    with pytest.raises(ValueError, match="重要性阈值 threshold 必须在"):
        await engine.evict(
            relational_storage=MagicMock(),
            vector_storage=MagicMock(),
            working_cache={},
            threshold=1.5
        )
    with pytest.raises(ValueError, match="重要性阈值 threshold 必须在"):
        await engine.evict(
            relational_storage=MagicMock(),
            vector_storage=MagicMock(),
            working_cache={},
            threshold=-0.1
        )

    # 3. max_age_days 非正数
    with pytest.raises(ValueError, match="最大存活天数 max_age_days 必须大于等于 1"):
        await engine.evict(
            relational_storage=MagicMock(),
            vector_storage=MagicMock(),
            working_cache={},
            max_age_days=0
        )


@pytest.mark.asyncio
async def test_eviction_engine_three_axis_execution():
    """验证三维淘汰引擎在 combined 模式下的协同清理逻辑"""
    engine = MemoryEvictionEngine()

    mock_relational = MagicMock()
    mock_relational.delete_low_importance = AsyncMock(return_value=4)
    mock_relational.delete_expired = AsyncMock(return_value=2)

    mock_vector = MagicMock()
    mock_vector.forget = AsyncMock(return_value=3)

    now_ts = datetime.now().timestamp()
    working_cache = {
        "valid_key": {"val": "fresh", "expire": now_ts + 3600},
        "expired_key_1": {"val": "old1", "expire": now_ts - 100},
        "expired_key_2": {"val": "old2", "expire": now_ts - 200},
    }

    report = await engine.evict(
        relational_storage=mock_relational,
        vector_storage=mock_vector,
        working_cache=working_cache,
        strategy="combined",
        threshold=0.25,
        max_age_days=15
    )

    # 验证各项维度清理计数
    assert report["importance_evicted"] == 7  # 4 + 3
    assert report["time_evicted"] == 2
    assert report["l0_expired"] == 2

    # 验证 cache 物理淘汰
    assert "expired_key_1" not in working_cache
    assert "expired_key_2" not in working_cache
    assert "valid_key" in working_cache

    mock_relational.delete_low_importance.assert_awaited_once_with(0.25)
    mock_vector.forget.assert_awaited_once_with(0.25)
    mock_relational.delete_expired.assert_awaited_once_with(15)


def test_health_inspector_metrics_and_summary():
    """验证健康巡检器生成的仪表盘度量与紧凑摘要格式"""
    inspector = MemoryHealthInspector()

    now_ts = datetime.now().timestamp()
    working_cache = {
        "k1": {"expire": now_ts + 1000},
        "k2": {"expire": now_ts + 2000},
        "k3": {"expire": now_ts - 100},  # 过期待清理
    }

    mock_perceptual = MagicMock()
    mock_perceptual._init_failed = False

    stats = inspector.inspect(
        working_cache=working_cache,
        perceptual_component=mock_perceptual,
        storage_pool={"tenant_a": {}, "tenant_b": {}},
        memory_mode="LOCAL",
        redis_client=None
    )

    assert stats["version"] == "V4.6.0"
    assert stats["memory_mode"] == "LOCAL"
    assert stats["layers"]["l0_working"]["active"] == 2
    assert stats["layers"]["l0_working"]["expired_pending_gc"] == 1
    assert stats["layers"]["l3_perceptual"]["status"] == "ONLINE"
    assert stats["infrastructure"]["tenant_shards"] == 2
    assert stats["infrastructure"]["redis"] == "OFFLINE"

    summary = inspector.format_summary(stats)
    assert "🧠 记忆中枢 [LOCAL]" in summary
    assert "L0工作记忆: 2项活跃" in summary
    assert "感知层: ONLINE" in summary
