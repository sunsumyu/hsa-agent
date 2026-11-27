"""
tests/unit/core/test_registry_load_race.py
==========================================
[P0-3 / P0-4] Prompt / Rule 注册表并发加载与 reload 窗口反向验证。

判定标准: 旧实现必然红灯。
- RoutingRuleRegistry._ensure_loaded 用 list.append 且从不清空 →
  并发首载产出重复路由规则 (业务结果错误, 非性能问题);
- get_rules 返回活的 list 本身 → 调用方遍历时并发 reload 的 clear 会静默跳过元素;
- reload 先 _cache.clear() 再重载 → 窗口内 get_entry / get 返回
  KeyError / None (提示词版本管理的 save/rollback 端点触发 reload 时业务中断)。
新实现: 双重检查锁 + 局部构建整体替换 (与 SchemaRegistry 同款)。
"""

import threading
import time
from pathlib import Path

import pytest
import yaml

from app.core.registry.prompt_registry import PromptRegistry
from app.core.registry.rule_registry import RoutingRuleRegistry, SQLTemplateRegistry


def _make_routing_registry(tmp_path: Path) -> RoutingRuleRegistry:
    data = {
        "rules": [
            {
                "target_id": f"rule_{i}",
                "route_type": "KNOWN_RULE",
                "exact_keywords": [f"k{i}"],
                "fuzzy_groups": [],
                "description": f"d{i}",
            }
            for i in range(2)
        ]
    }
    cfg = tmp_path / "routing_rules.yaml"
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    return RoutingRuleRegistry(config_path=cfg)


def test_concurrent_first_load_yields_no_duplicate_routing_rules(tmp_path):
    reg = _make_routing_registry(tmp_path)
    N = 8
    barrier = threading.Barrier(N)
    results = [None] * N

    def worker(i):
        barrier.wait(timeout=5)
        results[i] = reg.get_rules()

    threads = [
        threading.Thread(target=worker, name=f"route-load-{i}", args=(i,))
        for i in range(N)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert all(not t.is_alive() for t in threads), "并发首载死锁"

    assert all(len(r) == 2 for r in results), (
        f"并发首载产出重复路由规则: {[len(r) for r in results]} "
        f"(旧实现 _rules.append 不清空 → 路由结果错误)"
    )


def test_get_rules_returns_snapshot_not_live_list(tmp_path):
    reg = _make_routing_registry(tmp_path)
    rules = reg.get_rules()
    assert len(rules) == 2
    rules.append("sentinel")  # 模拟调用方持有/修改返回列表
    assert len(reg.get_rules()) == 2, (
        "get_rules 返回活引用: 调用方遍历时并发 reload 的 clear 会静默跳过元素"
    )


def _make_prompt_registry(tmp_path: Path) -> PromptRegistry:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    with open(prompts_dir / "p1.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"id": "p1", "version": "1.0.0", "system_template": "hello"}, f)
    return PromptRegistry(prompts_dir=prompts_dir)


def _spy_cache(reg, attr: str, cleared: threading.Event):
    """把注册表缓存换成带 clear 钩子的 SpyDict, 放大旧实现 reload 的清空窗口。

    旧实现 reload 走 _cache.clear() → 钩子触发; 新实现局部构建整体替换, 不再调 clear。
    """

    class SpyDict(dict):
        def clear(self):
            super().clear()
            cleared.set()
            time.sleep(0.05)  # 放大 clear → _loaded=False 之间的窗口

    setattr(reg, attr, SpyDict(getattr(reg, attr)))
    return SpyDict


def test_prompt_reload_never_exposes_cleared_cache(tmp_path):
    reg = _make_prompt_registry(tmp_path)
    assert reg.get_entry("p1").prompt_id == "p1"  # 完成首载

    cleared = threading.Event()
    _spy_cache(reg, "_cache", cleared)

    outcome = {}

    def reloader():
        reg.reload()

    def reader():
        cleared.wait(timeout=1.0)
        try:
            outcome["entry"] = reg.get_entry("p1")
        except KeyError as e:
            outcome["keyerror"] = str(e)

    t_reload = threading.Thread(target=reloader, name="prompt-reload")
    t_read = threading.Thread(target=reader, name="prompt-read")
    t_read.start()
    t_reload.start()
    t_reload.join(timeout=5)
    t_read.join(timeout=5)
    assert not t_reload.is_alive() and not t_read.is_alive(), "reload 并发路径死锁"

    assert "keyerror" not in outcome, (
        f"reload 清空窗口内 get_entry KeyError (业务中断): {outcome.get('keyerror')}"
    )
    assert outcome["entry"].prompt_id == "p1"


def test_sql_template_reload_never_exposes_cleared_cache(tmp_path):
    data = {
        "templates": {
            "RULE_A": {"sql_template": "SELECT 1 FROM {table}", "description": "t"}
        }
    }
    (tmp_path / "sql_templates.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    reg = SQLTemplateRegistry(rules_dir=tmp_path)
    assert reg.get("rule_a") is not None  # 完成首载

    cleared = threading.Event()
    _spy_cache(reg, "_cache", cleared)

    outcome = {}

    def reloader():
        reg.reload()

    def reader():
        cleared.wait(timeout=1.0)
        outcome["entry"] = reg.get("rule_a")

    t_reload = threading.Thread(target=reloader, name="sql-reload")
    t_read = threading.Thread(target=reader, name="sql-read")
    t_read.start()
    t_reload.start()
    t_reload.join(timeout=5)
    t_read.join(timeout=5)
    assert not t_reload.is_alive() and not t_read.is_alive(), "reload 并发路径死锁"

    assert outcome["entry"] is not None, (
        "reload 清空窗口内 get 返回 None (旧实现先 clear 再重载 → SQL 模板静默失配)"
    )
