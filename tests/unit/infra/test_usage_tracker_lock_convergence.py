"""
tests/unit/infra/test_usage_tracker_lock_convergence.py
=======================================================
[P0-1] UsageTracker 锁收敛反向验证。

背景: 构造时 ModelHealthGovernor 按引用持有 stats.blacklist_expiry /
stats.stability_scores 同一份 dict, 而 _save_stats → model_dump_json 会迭代这些 dict。
旧实现只有 record_usage 持锁, 其余写路径 (reset_blacklists / record_failure /
record_success / check_limit / should_run_startup_probe) 全部绕过锁:
  - 在序列化迭代期间并发 clear()/pop() 共享 dict → RuntimeError (统计链路抛崩);
  - record_failure 的 read → -0.2 → write 并发丢更新 → 熔断该触发时不触发。
判定标准: 旧实现必然红灯; 新实现 (写路径收敛到 tracker._lock 单一互斥域) 全绿。
"""

import threading
import time
from pathlib import Path

import pytest

from app.core.schemas import ModelConfig
from app.infra.usage_tracker import UsageTracker


def _make_tracker(tmp_path: Path) -> UsageTracker:
    tracker = UsageTracker(
        stats_path=str(tmp_path / "stats.json"),
        config_path="non_existent.json",
        role_path="non_existent.json",
    )
    tracker.model_configs = {
        "m-01": ModelConfig(
            id="m-01",
            provider="test",
            model_name="m-01",
            family="test",
            platform="test",
            api_key_env="TEST_KEY",
            daily_quota=100000,
            input_cost_1k=0.001,
            output_cost_1k=0.002,
            is_active=True,
        )
    }
    # 预置黑名单, 保证 governor 与 stats 共享的 dict 非空;
    # 两条记录: 干净迭代时第二次 next() 仍有元素, 与"迭代期间被 clear"的
    # RuntimeError 路径严格可区分 (单条记录下干净的第二次 next 会 StopIteration)
    tracker.stats.blacklist_expiry["m-01"] = time.time() + 999
    tracker.stats.blacklist_expiry["m-02"] = time.time() + 999
    return tracker


def test_reset_blacklists_is_mutually_exclusive_with_locked_save(tmp_path):
    """A 线程持锁序列化 stats 时, B 线程 reset_blacklists 必须被互斥。

    旧实现: B 无锁并发 clear() governor 共享的 dict → A 的迭代抛 RuntimeError。
    新实现: B 阻塞在 tracker._lock 上, A 释放后 clear 才落地, 迭代完整。
    """
    tracker = _make_tracker(tmp_path)
    shared = tracker.stats.blacklist_expiry
    assert shared, "前置: 共享黑名单 dict 必须非空"

    a_in_save = threading.Event()
    b_doorstep = threading.Event()
    b_done = threading.Event()
    outcome = {}
    thread_a_holder = [None]

    original_save = tracker._save_stats

    def choreographed_save():
        # 仅对 A 线程的调用做编排; B 线程 governor 回调的 on_persist 走原实现
        if threading.current_thread() is not thread_a_holder[0]:
            original_save()
            return
        # 模拟 model_dump_json 在持锁状态下迭代共享 dict:
        # 迭出第一个元素后放行 B; 若 B 无锁并发 clear(), 继续迭代必抛 RuntimeError
        items = iter(shared.items())
        next(items)
        a_in_save.set()
        assert b_doorstep.wait(timeout=5), "B 线程未能在 5s 内抵达 reset 入口"
        time.sleep(0.3)  # 旧实现: B 在此窗口内无锁清空 dict → 下一轮迭代必炸
        try:
            next(items)
            outcome["raced"] = False
        except RuntimeError:
            outcome["raced"] = True

    tracker._save_stats = choreographed_save

    def worker_a():
        thread_a_holder[0] = threading.current_thread()
        try:
            tracker.record_usage("m-01", 100, 50)
        except RuntimeError as e:
            outcome["a_error"] = str(e)

    def worker_b():
        assert a_in_save.wait(timeout=5), "A 线程未进入持锁序列化临界区"
        b_doorstep.set()
        tracker.reset_blacklists()
        b_done.set()

    ta = threading.Thread(target=worker_a, name="a-record-usage")
    tb = threading.Thread(target=worker_b, name="b-reset-blacklists")
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)
    assert not ta.is_alive() and not tb.is_alive(), "并发路径死锁"

    assert "a_error" not in outcome, f"record_usage 链路抛崩: {outcome.get('a_error')}"
    assert b_done.is_set(), "B 线程的 reset 必须完成"
    assert outcome.get("raced") is False, (
        "旧实现: B 线程在 A 持锁迭代共享 dict 期间无锁 clear() (RuntimeError 竞态)"
    )
    assert tracker.stats.blacklist_expiry == {}, "B 的 reset 最终必须落地"


def test_concurrent_record_failure_keeps_every_deduction(tmp_path):
    """并发 record_failure 的 read → -0.2 → write 窗口不得丢扣分。

    旧实现: 健康分扣分绕过锁, N 次并发只落 1 次扣分 → 熔断漏触发。
    新实现: 扣分在 tracker._lock 内串行, N 次扣分精确累加。
    """
    tracker = _make_tracker(tmp_path)
    governor = tracker._governor
    original_get = governor.get_stability_score

    def slow_get(model_id):
        # 先读后睡: 精确放大 read → write 之间的窗口 (睡在读前不构成 RMW 竞态)
        value = original_get(model_id)
        time.sleep(0.05)
        return value

    governor.get_stability_score = slow_get

    N = 5
    barrier = threading.Barrier(N)

    def worker():
        barrier.wait(timeout=5)
        tracker.record_failure("m-01", "timeout")  # 非致命错误 → 走健康分扣减路径

    threads = [threading.Thread(target=worker, name=f"failure-{i}") for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert all(not t.is_alive() for t in threads), "record_failure 并发路径死锁"

    final = tracker.stats.stability_scores["m-01"]
    assert final == pytest.approx(0.0), (
        f"并发扣分丢失: {N} 次 -0.2 后应为 0.0, 实际 {final} "
        f"(旧实现 read-modify-write 丢更新 → 熔断漏触发)"
    )
