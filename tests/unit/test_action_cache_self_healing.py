# -*- coding: utf-8 -*-
"""
TDD Suite 1: ActionCache Self-Healing & Fingerprint Contract Tests
===================================================================
Driven by: docs/SPEC_DETERMINISTIC_CACHE_AND_SCHEMA_SEAMS.md
Testing Seam: ActionCacheManager.get_or_compute & contract assertion

断言目标:
1. 当缓存记录的 prompt/schema 指纹与当前系统不匹配时，缓存必须拒绝命中，触发重新生成并写回更新；
2. 当缓存中含有带 LIMIT 的 SQL，且当前任务为全量普查（Census）时，断言读取时契约检查拒绝该缓存，并将其从存储中淘汰（Evict）。
"""
import os
import pytest
import json
from app.core.memory.semantic_memory import ActionCacheManager


class TestActionCacheSelfHealing:
    """验证动作缓存深模块的自愈与指纹契约"""

    @pytest.fixture
    def temp_cache_file(self, tmp_path):
        cache_path = tmp_path / "test_action_cache.json"
        return str(cache_path)

    def test_cache_miss_and_refresh_on_fingerprint_mismatch(self, temp_cache_file):
        """
        [红灯测试 1] 指纹变更触发失效：
        预置一条旧指纹（例如 prompt_version='1.0'）的缓存项。
        当系统以新指纹（'1.1'）读取时，缓存必须判定失效，并调用生成器更新缓存文件。
        """
        manager = ActionCacheManager(cache_file=temp_cache_file)
        # 预置旧缓存
        initial_cache = [{
            "question": "排查男性结算妇科专属药品",
            "sql": "SELECT psn_no FROM fqz_fymx_test LIMIT 1000",
            "prompt_version": "1.0",
            "schema_hash": "hash_old",
            "archetype_tag": "mutex"
        }]
        with open(temp_cache_file, "w", encoding="utf-8") as f:
            json.dump(initial_cache, f, ensure_ascii=False)

        manager = ActionCacheManager(cache_file=temp_cache_file)

        # 当前环境使用新版本 1.1
        current_fingerprint = {
            "prompt_version": "1.1",
            "schema_hash": "hash_old"
        }

        # 预期深模块接口具有 get_or_compute
        assert hasattr(manager, "get_or_compute"), "ActionCacheManager 缺少深模块接口 get_or_compute！"

        new_sql_called = False
        def mock_compute():
            nonlocal new_sql_called
            new_sql_called = True
            return "SELECT count(*) FROM fqz_fymx_test"

        result_sql = manager.get_or_compute(
            question="排查男性结算妇科专属药品",
            fingerprint=current_fingerprint,
            computer=mock_compute
        )

        assert new_sql_called is True, "指纹不匹配时未触发重新生成！"
        assert "LIMIT 1000" not in result_sql, "返回了旧版本的脏 SQL！"

    def test_evict_poisonous_limit_cache_in_census_task(self, temp_cache_file):
        """
        [红灯测试 2] 读取时契约断言：
        若缓存中的 SQL 含有 LIMIT，而任务被指定为全量普查（census），必须判定不合规，
        从物理存储中淘汰（Evict）该脏缓存，并触发重新生成。
        """
        manager = ActionCacheManager(cache_file=temp_cache_file)
        initial_cache = [{
            "question": "全国医保标准行政区划代码字典层级普查",
            "sql": "SELECT * FROM fqz_admdvs LIMIT 50",
            "prompt_version": "1.1",
            "schema_hash": "hash_current",
            "archetype_tag": "census"
        }]
        with open(temp_cache_file, "w", encoding="utf-8") as f:
            json.dump(initial_cache, f, ensure_ascii=False)

        manager = ActionCacheManager(cache_file=temp_cache_file)

        assert hasattr(manager, "get_or_compute"), "ActionCacheManager 缺少深模块接口 get_or_compute！"

        # 校验器断言：普查任务严禁包含 LIMIT
        def census_validator(sql: str) -> bool:
            return "LIMIT" not in sql.upper()

        computed = False
        def mock_compute():
            nonlocal computed
            computed = True
            return "SELECT admdvs_lv, count(*) FROM fqz_admdvs GROUP BY admdvs_lv"

        result = manager.get_or_compute(
            question="全国医保标准行政区划代码字典层级普查",
            fingerprint={"prompt_version": "1.1", "schema_hash": "hash_current"},
            validator=census_validator,
            computer=mock_compute
        )

        assert computed is True, "含有 LIMIT 的全量普查缓存未被拒绝！"
        assert "LIMIT" not in result.upper()
