"""
tests/unit/memory/test_working_memory_deep_red.py
=================================================
[Matt Pocock Deep Module Red Test] 二级工作记忆 (L0本地内存 + L1 Redis分布式) 深模块架构测试
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
from app.core.memory.types.working import WorkingMemory
from app.core.memory.manager import memory_hub


def test_working_memory_l0_store_and_recall():
    """验证纯本地 L0 模式下的存储与即时召回"""
    wm = WorkingMemory(redis_client=None)

    wm.store("case_001", {"audit_status": "FLAGGED", "rule": "GENDER_CONFLICT"}, ttl=10)

    val = wm.recall("case_001")
    assert val is not None
    assert val["audit_status"] == "FLAGGED"
    assert val["rule"] == "GENDER_CONFLICT"


def test_working_memory_l1_redis_penetration_and_backfill():
    """验证 L0 未命中或过期时穿透至 Redis L1 并反向预热 L0"""
    mock_redis = MagicMock()
    mock_client = MagicMock()
    mock_redis.client = mock_client

    # 模拟 Redis 中存在持久化序列化数据
    mock_client.get.return_value = '{"hospital_id": "H889", "risk_level": "HIGH"}'

    wm = WorkingMemory(redis_client=mock_redis)

    # 本地 L0 此时无该 key
    assert "target_hosp" not in wm.cache

    # 执行召回，穿透到 Redis
    res = wm.recall("target_hosp")

    assert res == {"hospital_id": "H889", "risk_level": "HIGH"}
    mock_client.get.assert_called_once_with("hsa:working:target_hosp")

    # 验证反向预热回本地 L0 缓存
    assert "target_hosp" in wm.cache
    assert wm.cache["target_hosp"]["val"] == res


def test_working_memory_search_and_expiration():
    """验证工作记忆词法模糊搜索与过期过滤"""
    wm = WorkingMemory(redis_client=None)

    # 写入一条有效记录
    wm.store("valid_key", "发现虚假住院与分解住院欺诈记录", ttl=60)

    # 写入一条过期记录
    now_ts = datetime.now().timestamp()
    wm.cache["expired_key"] = {
        "val": "分解住院历史线索",
        "expire": now_ts - 10,  # 已过期
    }

    # 执行词法搜索
    hits = wm.search(query="分解住院", limit=5)

    # 只有 valid_key 应该被召回，expired_key 被忽略
    assert len(hits) == 1
    assert hits[0].memory_type == "working"
    assert hits[0].metadata["key"] == "valid_key"
    assert "分解住院" in hits[0].content


def test_memory_hub_working_memory_facade_delegation():
    """验证 MemoryHub 原有 store_working, recall_working, search_working 保持无缝兼容"""
    memory_hub.store_working("hub_test_key", {"score": 99}, ttl=60)

    val = memory_hub.recall_working("hub_test_key")
    assert val == {"score": 99}

    # 验证 working_cache 字典引用与底层完全一致
    assert "hub_test_key" in memory_hub.working_cache
    assert memory_hub.working_cache["hub_test_key"]["val"] == {"score": 99}

    results = memory_hub.search_working("score", limit=1)
    assert len(results) >= 1
    assert results[0].memory_type == "working"
