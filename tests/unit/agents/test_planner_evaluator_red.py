"""
tests/unit/agents/test_planner_evaluator_red.py
================================================
[SPEC-227 / Matt Pocock Deep Module] 规划器动作缓存仲裁与响应解析深模块测试 (红灯先行)
"""

import pytest
from app.agents.planner_evaluator import (
    evaluate_action_cache,
    parse_planner_response,
)


def test_parse_planner_response_with_sections():
    """测试标准章节格式解析：分离 METHODOLOGY 与 TASKS"""
    content = (
        "### METHODOLOGY\n"
        "采用时序滑动窗口与限定性别条件排查门诊异常结算。\n"
        "### TASKS\n"
        "1. 查询 fqz_fymx_test 基础流水\n"
        "2. 过滤 gend = '1' 且药品涉及妇科\n"
        "3. 汇总违规金额与人数"
    )
    methodology, tasks = parse_planner_response(content)
    assert methodology == "采用时序滑动窗口与限定性别条件排查门诊异常结算。"
    assert len(tasks) == 3
    assert tasks[0] == "查询 fqz_fymx_test 基础流水"
    assert tasks[1] == "过滤 gend = '1' 且药品涉及妇科"
    assert tasks[2] == "汇总违规金额与人数"


def test_parse_planner_response_plain_list():
    """测试纯任务列表格式解析"""
    content = (
        "- 执行全量违规排查 SQL\n"
        "* 统计违规总金额\n"
        "3. 校验检出指标"
    )
    methodology, tasks = parse_planner_response(content)
    assert methodology == ""
    assert len(tasks) == 3
    assert tasks[0] == "执行全量违规排查 SQL"
    assert tasks[1] == "统计违规总金额"
    assert tasks[2] == "校验检出指标"


def test_evaluate_action_cache_stale_version(monkeypatch):
    """测试缓存版本指纹陈旧时跳过缓存"""
    fake_candidate = {
        "prompt_version": "1.0",
        "sql": "SELECT 1",
        "tasks": ["执行旧规划"],
    }
    class MockCacheMgr:
        def search(self, q):
            return fake_candidate
        def evict(self, q):
            pass

    monkeypatch.setattr("app.core.memory.semantic_memory.action_cache_manager", MockCacheMgr())
    result = evaluate_action_cache("排查男性妇科结算", target_prompt_ver="2.0")
    assert result is None


def test_evaluate_action_cache_dirty_limit_evicted(monkeypatch):
    """测试全量排查任务遇到带 LIMIT 的脏缓存时触发物理淘汰"""
    evicted_keys = []
    fake_candidate = {
        "prompt_version": "2.0",
        "sql": "SELECT * FROM fqz_fymx_test LIMIT 10",
        "question": "全量排查男性妇科",
        "tasks": ["查询抽样流水"],
    }
    class MockCacheMgr:
        def search(self, q):
            return fake_candidate
        def evict(self, q):
            evicted_keys.append(q)

    monkeypatch.setattr("app.core.memory.semantic_memory.action_cache_manager", MockCacheMgr())
    result = evaluate_action_cache("全量排查男性妇科", target_prompt_ver="2.0")
    assert result is None
    assert "全量排查男性妇科" in evicted_keys


def test_evaluate_action_cache_hit_valid(monkeypatch):
    """测试有效经验缓存命中并生成标准证据链结果"""
    fake_candidate = {
        "prompt_version": "2.0",
        "sql": "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend = '1' GROUP BY psn_no",
        "tasks": ["执行全量分组统计"],
        "methodology": "性别排他全量对碰",
    }
    class MockCacheMgr:
        def search(self, q):
            return fake_candidate
        def evict(self, q):
            pass

    monkeypatch.setattr("app.core.memory.semantic_memory.action_cache_manager", MockCacheMgr())
    result = evaluate_action_cache("核查男性妇科", target_prompt_ver="2.0")
    assert result is not None
    assert result["cache_hit"] is True
    assert result["sql_query"] == fake_candidate["sql"]
    assert result["sql_history"] == [fake_candidate["sql"]]
    assert result["tasks"] == ["执行全量分组统计"]
