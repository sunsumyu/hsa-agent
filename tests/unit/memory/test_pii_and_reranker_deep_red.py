"""
tests/unit/memory/test_pii_and_reranker_deep_red.py
===================================================
[Matt Pocock Deep Module Red Test] 记忆中枢 PII 脱敏与启发式混合重排器解耦架构测试
"""

from datetime import datetime, timedelta
import pytest
from app.core.memory.base import MemoryItem
from app.core.memory.pii_scrubber import PIIScrubber, pii_scrubber
from app.core.memory.hybrid_reranker import HybridReranker, hybrid_reranker
from app.core.memory.manager import memory_hub


def test_pii_scrubber_masking_comprehensive():
    """验证 PII 物理脱敏算子对五类敏感实体的掩码隔离能力"""
    scrubber = PIIScrubber()

    raw_text = (
        "患者: 张三丰 在 13812345678 的手机通知下，"
        "持身份证 110101199003072345 以及医保卡 6222021234567890123 进行结算，"
        "电子信箱为 doctor.zhang@hospital.org.cn。"
    )

    masked = scrubber.mask_sensitive_data(raw_text)

    # 1. 身份证前6后2
    assert "110101********45" in masked
    assert "110101199003072345" not in masked

    # 2. 手机前3后4
    assert "138****5678" in masked
    assert "13812345678" not in masked

    # 3. 医保卡仅保留后4位
    assert "**** **** **** 0123" in masked
    assert "6222021234567890123" not in masked

    # 4. 邮箱
    assert "****@hospital.org.cn" in masked
    assert "doctor.zhang@" not in masked

    # 5. 姓名
    assert "患者: 张**" in masked

    # 空值安全
    assert scrubber.mask_sensitive_data("") == ""
    assert scrubber.mask_sensitive_data(None) == ""


def test_hybrid_reranker_scoring_and_deduplication():
    """验证启发式重排器的加权综合打分、关键字激励与哈希去重截断"""
    reranker = HybridReranker()
    now = datetime.now()

    item1 = MemoryItem(
        content="患者住院期间重复收费头孢曲松钠注射液",
        memory_type="semantic",
        importance=0.9,
        timestamp=now - timedelta(days=1),
        score=0.8,
    )
    # item2 为 item1 内容的重复项
    item2 = MemoryItem(
        content="患者住院期间重复收费头孢曲松钠注射液",
        memory_type="semantic",
        importance=0.4,
        timestamp=now - timedelta(days=10),
        score=0.5,
    )
    # item3 为无硬匹配且时间久远的项目
    item3 = MemoryItem(
        content="普通门诊挂号费正常收取无违规",
        memory_type="semantic",
        importance=0.1,
        timestamp=now - timedelta(days=60),
        score=0.3,
    )

    query = "头孢曲松钠 重复收费 审计"
    ranked = reranker.rerank(query=query, candidates=[item1, item2, item3], limit=2)

    # 必须执行物理去重，去重后 item1 与 item2 仅保留 1 条最高分
    assert len(ranked) == 2
    assert ranked[0].content == item1.content
    assert ranked[0].metadata.get("rerank_score") is not None
    assert ranked[0].metadata["rerank_score"] > ranked[1].metadata["rerank_score"]


def test_memory_hub_facade_delegation():
    """验证 MemoryHub 原有方法无缝透明委托至新深模块"""
    # 验证脱敏委托
    masked_hub = memory_hub._mask_sensitive_data("手机 13912345678")
    assert "139****5678" in masked_hub

    # 验证重排委托
    candidates = [
        MemoryItem(content="A", memory_type="semantic", importance=0.8, timestamp=datetime.now(), score=0.9),
        MemoryItem(content="B", memory_type="semantic", importance=0.2, timestamp=datetime.now(), score=0.3),
    ]
    reranked = memory_hub._rerank_results("A", candidates, limit=1)
    assert len(reranked) == 1
    assert reranked[0].content == "A"
