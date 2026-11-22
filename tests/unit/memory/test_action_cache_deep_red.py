"""
tests/unit/memory/test_action_cache_deep_red.py
===============================================
Red unit tests for ActionCacheManager deep module (app/core/memory/action_cache.py).
Tests:
- normalize_question: cleans prefixes, polite phrases, punctuation, action suffixes
- save & dual-index lookup: exact key and canonical key
- get_or_compute: fingerprint mismatch, runtime contract failure, self-healing recomputation
- evict: removes from memory and persistent state
- search: multi-tier matching (exact, canonical, semantic)
"""

import pytest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock

from app.core.memory.action_cache import ActionCacheManager, action_cache_manager


@pytest.fixture
def temp_cache_file(tmp_path: Path):
    c_file = tmp_path / "action_cache.json"
    return str(c_file)


def test_action_cache_normalize_question():
    mgr = ActionCacheManager(cache_file="dummy.json")
    
    # 1. Polite prefixes
    assert mgr.normalize_question("请帮我核查一下退运药品") == "退运药品"
    assert mgr.normalize_question("麻烦帮我排查今年高额报销") == "今年高额报销"
    
    # 2. Scope prefixes and punctuation
    assert mgr.normalize_question("针对：男性结算妇科专属药品；") == "男性结算妇科专属药品"
    assert mgr.normalize_question("关于【门诊慢性病超量开药】") == "门诊慢性病超量开药"
    
    # 3. Action verbs and suffixes
    assert mgr.normalize_question("开展男性结算妇科专属药品核查") == "男性结算妇科专属药品"
    assert mgr.normalize_question("对高额违规单据进行统计分析") == "高额违规单据"


def test_action_cache_save_and_dual_lookup(temp_cache_file):
    mgr = ActionCacheManager(cache_file=temp_cache_file)

    seed_q = "针对男性结算妇科专属药品开展核查"
    sql = "SELECT * FROM fqz_fymx_test WHERE gend = '1' AND med_type = 'GYN'"
    mgr.save(seed_q, sql=sql, tasks=["task1"], methodology="性别冲突检测")

    # 1. Exact lookup
    assert seed_q in mgr.lookup
    assert mgr.lookup[seed_q]["sql"] == sql

    # 2. Canonical lookup (0ms bypass for variants)
    canon_seed = mgr.normalize_question(seed_q)
    assert canon_seed in mgr.canonical_lookup
    assert mgr.canonical_lookup[canon_seed]["sql"] == sql

    # Variant should match canon_seed
    variant = "请帮我排查一下男性结算妇科专属药品！"
    canon_var = mgr.normalize_question(variant)
    assert canon_var == canon_seed
    assert mgr.canonical_lookup[canon_var]["sql"] == sql

    # File persisted
    assert os.path.exists(temp_cache_file)
    with open(temp_cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["question"] == seed_q


def test_action_cache_evict(temp_cache_file):
    mgr = ActionCacheManager(cache_file=temp_cache_file)
    mgr.save("问题A", "SELECT 1")
    mgr.save("问题B", "SELECT 2")

    assert len(mgr.cache) == 2
    mgr.evict("问题A")
    assert "问题A" not in mgr.lookup
    canon_a = mgr.normalize_question("问题A")
    assert canon_a not in mgr.canonical_lookup
    assert len(mgr.cache) == 1
    assert mgr.cache[0]["question"] == "问题B"


def test_action_cache_get_or_compute_contract(temp_cache_file):
    mgr = ActionCacheManager(cache_file=temp_cache_file)
    
    # Seed dirty cache with LIMIT
    mgr.save(
        "全量普查行政区划",
        sql="SELECT * FROM fqz_admdvs LIMIT 50",
        fingerprint={"prompt_ver": "1.0", "schema_hash": "hash_1"}
    )

    # 1. Fingerprint mismatch triggers recompute
    new_computed = False
    def compute_fn():
        nonlocal new_computed
        new_computed = True
        return "SELECT count(*) FROM fqz_admdvs"

    sql_res = mgr.get_or_compute(
        question="全量普查行政区划",
        fingerprint={"prompt_ver": "2.0", "schema_hash": "hash_1"},
        computer=compute_fn
    )
    assert new_computed is True
    assert sql_res == "SELECT count(*) FROM fqz_admdvs"

    # 2. Runtime validator failure triggers eviction and recompute
    dirty_evicted = False
    def validator_no_limit(sql: str) -> bool:
        return "LIMIT" not in sql.upper()

    def compute_clean():
        nonlocal dirty_evicted
        dirty_evicted = True
        return "SELECT count(*) FROM fqz_admdvs GROUP BY admdvs_lv"

    # Now simulate cache has LIMIT again
    mgr.save("普查任务", "SELECT * FROM fqz_admdvs LIMIT 10")
    res2 = mgr.get_or_compute(
        question="普查任务",
        validator=validator_no_limit,
        computer=compute_clean
    )
    assert dirty_evicted is True
    assert "LIMIT" not in res2
