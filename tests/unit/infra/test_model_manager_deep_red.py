"""
tests/unit/infra/test_model_manager_deep_red.py
==============================================
Matt Pocock 风格契约测试：
验证模型基础设施层解耦出来的 LLMFactory 多提供者工厂、EndpointProber 主动探活自愈器，
以及 ModelManager 门面的复杂度分类与寻址协作。
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.schemas import ModelConfig, EndpointConfig
from app.infra.llm_factory import LLMFactory
from app.infra.endpoint_prober import EndpointProber
from app.infra.model_manager import ModelManager


class TestModelManagerDeepModules:
    def test_llm_factory_credentials_resolution(self, monkeypatch):
        factory = LLMFactory()

        cfg = ModelConfig(
            id="node-1",
            provider="openai",
            model_name="gpt-4o",
            family="gpt",
            platform="openai",
            api_key_env="CUSTOM_OPENAI_KEY",
            base_url_env="CUSTOM_OPENAI_URL",
        )

        # 1. 优先使用专属环境变量
        monkeypatch.setenv("CUSTOM_OPENAI_KEY", "sk-custom-123")
        monkeypatch.setenv("CUSTOM_OPENAI_URL", "https://api.custom.com/v1")
        key, url = factory.resolve_credentials(cfg)
        assert key == "sk-custom-123"
        assert url == "https://api.custom.com/v1"

        # 2. 缺失时回退到通用环境变量
        monkeypatch.delenv("CUSTOM_OPENAI_KEY")
        monkeypatch.delenv("CUSTOM_OPENAI_URL")
        monkeypatch.setenv("LLM_API_KEY", "sk-fallback-456")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.fallback.com/v1")
        key2, url2 = factory.resolve_credentials(cfg)
        assert key2 == "sk-fallback-456"
        assert url2 == "https://api.fallback.com/v1"

        # 3. 完全无 key 时返回 None
        monkeypatch.delenv("LLM_API_KEY")
        key3, _ = factory.resolve_credentials(cfg)
        assert key3 is None

    def test_llm_factory_create_missing_key_returns_none(self, monkeypatch):
        factory = LLMFactory()
        cfg = ModelConfig(
            id="node-no-key",
            provider="openai",
            model_name="gpt-4o",
            family="gpt",
            platform="openai",
            api_key_env="NON_EXISTENT_KEY_VAR",
        )
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        llm = factory.create_llm("node-no-key", cfg)
        assert llm is None

    def test_model_manager_classify_complexity_locally(self):
        mm = ModelManager(config_path="non_existent.json")

        # 高复杂度信号
        assert mm.classify_complexity_locally("请深入分析该医院是否存在家族套保欺诈环路与团伙关联") == "HIGH"
        assert mm.classify_complexity_locally("调用联邦图谱对跨机构骗保行为进行图分析") == "HIGH"
        # 超过 200 字符文本
        long_query = "医保基金审计核查" * 30
        assert mm.classify_complexity_locally(long_query) == "HIGH"

        # 低复杂度信号
        assert mm.classify_complexity_locally("查一下性别冲突记录总数") == "LOW"
        assert mm.classify_complexity_locally("显示重复收费数量") == "LOW"

        # 默认中等复杂度
        assert mm.classify_complexity_locally("评估参保人高频慢病配药行为合理性") == "MEDIUM"
        assert mm.classify_complexity_locally("") == "MEDIUM"

    @pytest.mark.asyncio
    async def test_endpoint_prober_recovers_cooling_node(self, monkeypatch):
        # 模拟单节点拨测成功
        prober = EndpointProber()

        mock_pool = MagicMock()
        mock_ep = MagicMock()
        mock_ep.id = "cooling-node-1"
        mock_ep.provider = "openai"
        mock_ep.model_name = "test-model"
        mock_pool.endpoints = [mock_ep]

        mock_pool_mgr = MagicMock()
        mock_pool_mgr.pools = {"pool-1": mock_pool}
        state = MagicMock()
        state.is_cooling = True
        mock_pool_mgr.states = {"cooling-node-1": state}
        mock_pool_mgr.record_success.side_effect = lambda ep: setattr(state, "is_cooling", False)

        mock_usage_tracker = MagicMock()
        mock_usage_tracker.blacklist_expiry = {"cooling-node-1": 9999999999.0}
        mock_usage_tracker.record_success.side_effect = lambda ep: mock_usage_tracker.blacklist_expiry.pop(ep, None)

        mock_redis = MagicMock()

        # 注入 mock 依赖 (patch 到 endpoint_prober 模块内部引用)
        monkeypatch.setattr("app.infra.endpoint_prober.endpoint_pool_manager", mock_pool_mgr)
        monkeypatch.setattr("app.infra.endpoint_prober.usage_tracker", mock_usage_tracker)
        monkeypatch.setattr("app.infra.endpoint_prober.redis_manager", mock_redis)

        # 模拟拨测 ping 成功
        prober._probe_single_endpoint = AsyncMock(return_value=True)

        await prober.probe_all_endpoints()

        # 应调用 record_success 恢复算力
        mock_pool_mgr.record_success.assert_called_once_with("cooling-node-1")
        mock_usage_tracker.record_success.assert_called_once_with("cooling-node-1")
        # 同步 Redis 为活跃
        mock_redis.record_node_health.assert_called_with("cooling-node-1", True)
