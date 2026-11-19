"""
tests/unit/memory/test_semantic_memory_decomposition_red.py
===========================================================
[TDD Red -> Green] 语义记忆与时间衰减评分解耦测试：
1. decay_scoring 纯函数计算 (L2 距离到相似度转换 + 指数时间衰减因子)
2. FaissVectorAdapter 向量索引动态加载与无感知容错
3. WorkingMemory 滚动窗口容量上限控制
4. CognitiveMemoryManager 联合召回与经验学习
"""

import pytest
from datetime import datetime, timedelta
from app.memory.decay_scoring import compute_decayed_score
from app.memory.faiss_vector_adapter import FaissVectorAdapter
from app.memory.semantic_memory import WorkingMemory, CognitiveMemoryManager


def test_decay_scoring_calculation():
    """验证时间衰减计算纯函数的确定性数学契约"""
    now = datetime(2026, 10, 19, 12, 0, 0)

    # 1. 当天发生的事件 (0 天)，raw_score = 0 (完全相同，相似度 1.0)
    score_today = compute_decayed_score(raw_l2_score=0.0, timestamp=now, decay_rate=0.05, now=now)
    assert pytest.approx(score_today, 0.001) == 1.0

    # 2. 10 天前的事件，衰减为 exp(-0.05 * 10) = exp(-0.5) ≈ 0.6065
    past_10d = now - timedelta(days=10)
    score_10d = compute_decayed_score(raw_l2_score=0.0, timestamp=past_10d, decay_rate=0.05, now=now)
    assert pytest.approx(score_10d, 0.001) == 0.6065

    # 3. 无时间戳默认降权因子 (0.8)
    score_no_ts = compute_decayed_score(raw_l2_score=0.0, timestamp=None, decay_rate=0.05, now=now)
    assert pytest.approx(score_no_ts, 0.001) == 0.8


def test_working_memory_capacity_sliding_window():
    """验证工作记忆按 capacity 进行滑动窗口保留"""
    wm = WorkingMemory(capacity=3)
    wm.add("item 1")
    wm.add("item 2")
    wm.add("item 3")
    assert len(wm.buffer) == 3
    assert wm.buffer[0].content == "item 1"

    # 添加第 4 项，最旧项 item 1 弹出
    wm.add("item 4")
    assert len(wm.buffer) == 3
    assert wm.buffer[0].content == "item 2"
    assert wm.buffer[-1].content == "item 4"


def test_faiss_vector_adapter_fallback():
    """验证向量适配器在底层索引缺失时返回空列表而非抛错"""
    adapter = FaissVectorAdapter()
    docs = adapter.search(
        storage_path="nonexistent_storage_path_test",
        embeddings=None,
        query="任意查询",
        k=2,
    )
    assert docs == []
