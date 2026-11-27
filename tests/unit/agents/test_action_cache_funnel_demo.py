"""
tests/unit/agents/test_action_cache_funnel_demo.py
====================================================
[演示测试] Planner 第一道漏斗"经验缓存命中"全链路演示
对应 app/agents/planner_agent.py 的 CACHE_CHECK 代码段 (L47-L55)。

覆盖路径：
1. ActionCacheManager 四级递进查找 (action_cache.py)：
   L0 内存字典精确命中 → L0.5 normalize_question 规范化指纹直通 →
   L1 Redis 分布式缓存 → L2 Embedding 语义相似度 (≥ 0.85)
2. planner_evaluator.evaluate_action_cache 双重仲裁：
   版本指纹陈旧拒绝 / 全量排查禁 LIMIT 脏缓存物理淘汰 / 有效命中产出计划字典
3. AuditPlannerAgent.plan() 命中缓存后的短路行为：
   不触达 FastRoute 与 LLM，直接携带 execution_trace 返回

Mock 边界 (遵循全链路重放测试原则)：仅隔离 Redis 网络与嵌入模型两类物理依赖，
缓存查找、指纹归一化、仲裁与淘汰、规划短路全部走真实实现。
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from loguru import logger

from app.agents.planner_evaluator import evaluate_action_cache
from app.core.memory.action_cache import ActionCacheManager


# ──────────────────────────────────────────────────────────
# 测试基础设施
# ──────────────────────────────────────────────────────────

class FakeRedisManager:
    """Redis 物理依赖桩：记录读写与淘汰，替代真实网络 IO"""

    def __init__(self):
        self.store = {}
        self.deleted = []

    def set_cache(self, key, value, expire_hours=24):
        self.store[key] = value

    def get_cache(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)


class _NoEmbedding:
    """禁用态嵌入引擎桩：__bool__ 为 False，阻断真实嵌入模型的懒加载"""

    def __bool__(self):
        return False

    def embed_query(self, text):
        return None


class FakeEmbeddingEngine:
    """受控向量桩：按关键词映射到 4 维语义象限，用于演示 L2 余弦命中"""

    _DIM_KEYWORDS = (("妇科", 0), ("结算", 1), ("药品", 2), ("目录", 3))

    def embed_query(self, text):
        vec = [0.0] * 4
        for kw, idx in self._DIM_KEYWORDS:
            if kw in text:
                vec[idx] = 1.0
        return vec


@contextmanager
def capture_logs():
    """捕获 loguru 日志流，用于断言命中的具体缓存层级"""
    records = []
    sink_id = logger.add(lambda msg: records.append(str(msg)), level="INFO")
    try:
        yield records
    finally:
        logger.remove(sink_id)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """全部用例统一替换 redis_manager 并固定缓存开关，保证离线确定性"""
    stub = FakeRedisManager()
    monkeypatch.setattr("app.core.memory.action_cache.redis_manager", stub)
    monkeypatch.setenv("DISABLE_AUDIT_CACHE", "false")
    return stub


def _fresh_manager(tmp_path) -> ActionCacheManager:
    """构建指向临时文件的全新缓存管理器，不触碰 data/action_cache.json 真实数据"""
    mgr = ActionCacheManager(cache_file=str(tmp_path / "action_cache.json"))
    mgr._engine = _NoEmbedding()  # 阻断真实嵌入引擎懒加载
    return mgr


def _patch_semantic_singleton(monkeypatch, mgr):
    """evaluate_action_cache 在函数体内从 semantic_memory 解析单例，替换为测试实例"""
    monkeypatch.setattr("app.core.memory.semantic_memory.action_cache_manager", mgr)


# ──────────────────────────────────────────────────────────
# 第一层演示：四级递进查找 (action_cache.py search)
# ──────────────────────────────────────────────────────────

def test_l0_exact_hit(fake_redis, tmp_path):
    """L0：完全相同的提问 → 内存字典精确命中，0ms 返回完整动作链"""
    mgr = _fresh_manager(tmp_path)
    mgr.save(
        "排查男性妇科结算异常",
        sql="SELECT psn_no FROM fqz_fymx WHERE gend = '1'",
        tasks=["执行性别排他核查"],
        methodology="性别排他全量对碰",
        fingerprint={"prompt_version": "2.0"},
    )
    with capture_logs() as logs:
        hit = mgr.search("排查男性妇科结算异常")

    assert hit is not None and hit["sql"].startswith("SELECT")
    assert any("字典精确命中" in line for line in logs)
    # save 时已同步写入 Redis 分布式层 (48h TTL)
    assert "action_cache:排查男性妇科结算异常" in fake_redis.store


def test_l05_canonical_fingerprint_hit(fake_redis, tmp_path):
    """L0.5：口语化变体命中规范化意图指纹——原文不同，剥离修饰后语义指纹一致"""
    mgr = _fresh_manager(tmp_path)
    saved = "全市男性妇科结算异常专项核查"
    query = "请帮我针对全市男性妇科结算异常专项核查一下！"
    assert query != saved  # 原文不同 → L0 必然失配
    mgr.save(saved, sql="SELECT 1", tasks=["t"], fingerprint={"prompt_version": "2.0"})

    # 指纹归一化：剥离"请帮我/针对/一下/核查"等口语修饰后完全一致
    assert mgr.normalize_question(query) == mgr.normalize_question(saved)

    with capture_logs() as logs:
        hit = mgr.search(query)

    assert hit is not None and hit["question"] == saved
    assert any("规范化意图直通命中" in line for line in logs)


def test_l1_redis_distributed_hit(fake_redis, tmp_path):
    """L1：本地无此条目，但分布式 Redis 中存在 (模拟另一 Worker 写入)"""
    mgr = _fresh_manager(tmp_path)
    # 种子条目保证本地 cache 非空 (search 对空 cache 直接短路)
    mgr.save("历史种子问题", sql="SELECT seed", fingerprint={"prompt_version": "2.0"})

    remote_payload = {
        "question": "跨进程共享的审计问题",
        "sql": "SELECT 2",
        "tasks": ["远端任务"],
        "prompt_version": "2.0",
    }
    fake_redis.store["action_cache:跨进程共享的审计问题"] = json.dumps(remote_payload, ensure_ascii=False)

    with capture_logs() as logs:
        hit = mgr.search("跨进程共享的审计问题")

    assert hit is not None and hit["sql"] == "SELECT 2"
    assert any("动作链缓存命中" in line for line in logs)


def test_l2_embedding_semantic_hit_and_miss(fake_redis, tmp_path):
    """L2：原文与指纹均未命中，靠向量余弦相似度兜底 (阈值 0.85)"""
    mgr = _fresh_manager(tmp_path)
    mgr._engine = FakeEmbeddingEngine()
    mgr.save("男性妇科结算异常专项核查", sql="SELECT 3", fingerprint={"prompt_version": "2.0"})

    # 同语义象限 (妇科+结算) → 余弦 1.0 ≥ 0.85 → 命中
    with capture_logs() as logs:
        hit = mgr.search("妇科结算异常线索摸排")
    assert hit is not None and hit["sql"] == "SELECT 3"
    assert any("语义命中" in line for line in logs)

    # 正交语义象限 (药品+目录) → 余弦 0 → 未命中
    assert mgr.search("药品目录维护操作指引") is None


# ──────────────────────────────────────────────────────────
# 第二层演示：evaluate_action_cache 双重仲裁 (planner_evaluator.py)
# ──────────────────────────────────────────────────────────

def test_arbitration_stale_version_rejected(fake_redis, monkeypatch, tmp_path):
    """仲裁①：缓存 prompt_version 指纹陈旧 (1.0 != 2.0) → 判定 Miss"""
    mgr = _fresh_manager(tmp_path)
    mgr.save("排查男性妇科结算异常", sql="SELECT 1", fingerprint={"prompt_version": "1.0"})
    _patch_semantic_singleton(monkeypatch, mgr)

    with capture_logs() as logs:
        result = evaluate_action_cache("排查男性妇科结算异常", target_prompt_ver="2.0")

    assert result is None
    assert any("缓存版本陈旧" in line for line in logs)


def test_arbitration_dirty_limit_physically_evicted(fake_redis, monkeypatch, tmp_path):
    """仲裁②：全量排查问题命中带 LIMIT 的抽样 SQL → 物理淘汰脏缓存"""
    mgr = _fresh_manager(tmp_path)
    mgr.save(
        "全量排查男性妇科结算",
        sql="SELECT * FROM fqz_fymx LIMIT 100",
        fingerprint={"prompt_version": "2.0"},
    )
    _patch_semantic_singleton(monkeypatch, mgr)

    with capture_logs() as logs:
        result = evaluate_action_cache("全量排查男性妇科结算", target_prompt_ver="2.0")

    assert result is None
    assert any("执行物理淘汰" in line for line in logs)
    # 物理淘汰三验证：内存索引、磁盘 JSON、Redis 副本均已清除
    assert mgr.cache == [] and mgr.lookup == {}
    assert "LIMIT" not in (tmp_path / "action_cache.json").read_text(encoding="utf-8")
    assert fake_redis.deleted == ["action_cache:全量排查男性妇科结算"]


def test_evaluate_returns_plan_on_valid_hit(fake_redis, monkeypatch, tmp_path):
    """仲裁通过 → 产出 planner 可直接消费的标准计划字典 (即 CACHE_CHECK 命中分支)"""
    mgr = _fresh_manager(tmp_path)
    sql = "SELECT psn_no, SUM(det_item_fee_sumamt) FROM fqz_fymx WHERE gend = '1' GROUP BY psn_no"
    mgr.save(
        "全市男性妇科结算异常专项核查",
        sql=sql,
        tasks=["执行性别排他对碰统计"],
        methodology="性别排他全量对碰",
        fingerprint={"prompt_version": "2.0"},
    )
    _patch_semantic_singleton(monkeypatch, mgr)

    # 口语化提问 → L0.5 指纹命中 → 指纹与契约双校验通过
    result = evaluate_action_cache("请帮我针对全市男性妇科结算异常专项核查一下！", target_prompt_ver="2.0")

    assert result["cache_hit"] is True
    assert result["sql_query"] == sql
    assert result["sql_history"] == [sql]
    assert result["tasks"] == ["执行性别排他对碰统计"]
    assert result["methodology"] == "性别排他全量对碰"
    assert result["messages"] == []


# ──────────────────────────────────────────────────────────
# 第三层演示：planner_agent.plan() 命中缓存后的短路 (被选中的 CACHE_CHECK 代码段)
# ──────────────────────────────────────────────────────────

async def test_planner_plan_short_circuit_on_cache_hit(fake_redis, monkeypatch, tmp_path):
    """命中经验缓存 → plan() 在第一道漏斗直接返回，不触达 FastRoute 与 LLM"""
    from app.agents.planner_agent import AuditPlannerAgent

    mgr = _fresh_manager(tmp_path)
    sql = "SELECT psn_no, SUM(det_item_fee_sumamt) FROM fqz_fymx WHERE gend = '1' GROUP BY psn_no"
    mgr.save(
        "全市男性妇科结算异常专项核查",
        sql=sql,
        tasks=["执行性别排他对碰统计"],
        methodology="性别排他全量对碰",
        fingerprint={"prompt_version": "2.0"},
    )
    _patch_semantic_singleton(monkeypatch, mgr)

    classify_calls = []

    class SpyRouter:
        def classify(self, q):
            classify_calls.append(q)
            raise AssertionError("缓存命中时不应触达 FastRoute")

    class BoomLLM:
        async def chat(self, **kwargs):
            raise AssertionError("缓存命中时不应调用 LLM")

    monkeypatch.setattr("app.agents.planner_agent.fast_router", SpyRouter())
    monkeypatch.setattr("app.agents.planner_agent.llm_provider", BoomLLM())

    agent = AuditPlannerAgent()
    state = {
        "session_id": "cache-hit-demo",
        "current_turn_query": "请帮我针对全市男性妇科结算异常专项核查一下！",
    }
    result = await agent.plan(state, SimpleNamespace())

    assert result["cache_hit"] is True
    assert result["tasks"] == ["执行性别排他对碰统计"]
    assert result["methodology"] == "性别排他全量对碰"
    assert result["sql_query"] == sql
    assert classify_calls == []  # 第二、三道漏斗全程未触达

    trace = "\n".join(result.get("execution_trace") or [])
    assert "PLANNER/CACHE_CHECK" in trace
    assert "命中经验缓存" in trace
