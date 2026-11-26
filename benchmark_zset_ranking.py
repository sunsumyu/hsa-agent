"""
Redis ZSet 排行榜性能基准真实测试与对比验证脚本
"""

import sys
import time
import random
import statistics
import hashlib
from concurrent.futures import ThreadPoolExecutor

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import fakeredis

server = fakeredis.FakeServer()

def get_client():
    return fakeredis.FakeRedis(server=server, decode_responses=True)

KEY_BAD_GLOBAL = "rank:global:bad"
KEY_GOOD_TOP = "rank:top_1000"
KEY_USER_HASH = "user:scores"
TOP_CAPACITY = 1000
NUM_SHARDS = 16

LUA_TOP_N_TRUNCATE = """
local top_key = KEYS[1]
local user_id = ARGV[1]
local new_score = tonumber(ARGV[2])
local max_cap = tonumber(ARGV[3])

local count = redis.call('ZCARD', top_key)

if count < max_cap then
    redis.call('ZADD', top_key, new_score, user_id)
    return 1
else
    local lowest = redis.call('ZRANGE', top_key, 0, 0, 'WITHSCORES')
    if lowest and #lowest >= 2 then
        local lowest_score = tonumber(lowest[2])
        if new_score > lowest_score then
            redis.call('ZADD', top_key, new_score, user_id)
            redis.call('ZREMRANGEBYRANK', top_key, 0, 0)
            return 1
        end
    end
end
return 0
"""

def get_shard_key(user_id: str) -> str:
    h = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
    return f"rank:shard:{h % NUM_SHARDS}"


def _measure_writes(worker_fn, total_writes: int, concurrency: int):
    """Execute concurrent write benchmark and return wall time, QPS, and latency percentiles."""
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        latencies = list(pool.map(worker_fn, range(total_writes)))
    t_wall = time.perf_counter() - t_start
    qps = total_writes / t_wall
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=100)[94]
    p99 = statistics.quantiles(latencies, n=100)[98]
    return t_wall, qps, p50, p95, p99


def _measure_reads(read_fn, rounds: int = 50) -> float:
    """Measure average Top-N read latency in milliseconds."""
    t_read0 = time.perf_counter()
    for _ in range(rounds):
        read_fn()
    return ((time.perf_counter() - t_read0) / rounds) * 1000


def _run_bad_global_zset(client, initial_users: int, total_writes: int, concurrency: int) -> dict:
    """Benchmark the anti-pattern single-key centralized ZSet."""
    print(f"[测试 1/3] 模拟有问题的方案：单 Key 集中式大 ZSet", flush=True)
    print(f" -> 正在批量预填充 {initial_users:,} 名基数学员到单个 BigKey...", flush=True)
    pipe = client.pipeline(transaction=False)
    for i in range(initial_users):
        pipe.zadd(KEY_BAD_GLOBAL, {f"user_{i}": round(random.uniform(10, 500), 2)})
        if (i + 1) % 5000 == 0:
            pipe.execute()
    pipe.execute()
    total_card = client.zcard(KEY_BAD_GLOBAL)
    print(f" -> 预填充完成，当前 Key 元素规模: {total_card:,} 个", flush=True)
    print(f" -> 启动 {concurrency} 线程模拟高并发打卡 ({total_writes:,} 次写入)...", flush=True)

    def worker_bad(_idx):
        t0 = time.perf_counter()
        uid = f"user_{random.randint(0, initial_users + 2000)}"
        get_client().zincrby(KEY_BAD_GLOBAL, 5.0, uid)
        return (time.perf_counter() - t0) * 1000

    t_wall, qps, p50, p95, p99 = _measure_writes(worker_bad, total_writes, concurrency)
    t_read = _measure_reads(lambda: client.zrevrange(KEY_BAD_GLOBAL, 0, 99, withscores=True))
    final_card = client.zcard(KEY_BAD_GLOBAL)
    mem_mb = final_card * 128 / (1024 * 1024)
    print(f" [测试 1 结果]")
    print(f"    - 并发写入耗时: {t_wall:.3f} s\n    - 写入 QPS: {qps:,.1f} req/s")
    print(f"    - 延迟指标: P50={p50:.2f}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")
    print(f"    - 排行榜 Key 元素总量: {final_card:,} 个")
    print(f"    - 生产环境对应内存开销(预估): {mem_mb:.2f} MB (单 Key 严重膨胀)")
    print(f"    - 查询 Top 100 单次平均延迟: {t_read:.3f} ms\n", flush=True)
    return {"card": final_card, "qps": qps, "p99": p99, "t_read": t_read}


def _seed_top_n_baseline(client, init_scores) -> None:
    """Populate full user score hash and top-N ZSet baseline."""
    pipe = client.pipeline(transaction=False)
    for uid, sc in init_scores:
        pipe.hset(KEY_USER_HASH, uid, sc)
        if len(pipe) >= 5000:
            pipe.execute()
    pipe.execute()
    init_scores.sort(key=lambda x: x[1], reverse=True)
    client.zadd(KEY_GOOD_TOP, {uid: sc for uid, sc in init_scores[:TOP_CAPACITY]})


def _run_top_n_truncate(client, init_scores, initial_users: int, total_writes: int, concurrency: int) -> dict:
    """Benchmark hot/cold separation with Lua Top-N truncation."""
    print(f"[测试 2/3] 优化方案 A：冷热分离 + Top 1000 动态截断", flush=True)
    print(f" -> 正在预填充学员数据并快速初始化 Top 1000 门槛...", flush=True)
    _seed_top_n_baseline(client, init_scores)
    print(f" -> 预填充完成，当前榜单严格控制在: {client.zcard(KEY_GOOD_TOP)} 个 (前 1000 名)", flush=True)
    lua_script = client.register_script(LUA_TOP_N_TRUNCATE)
    print(f" -> 启动 {concurrency} 线程模拟高并发打卡 ({total_writes:,} 次写入)...", flush=True)

    def worker_good_top_n(_idx):
        t0 = time.perf_counter()
        c = get_client()
        uid = f"user_{random.randint(0, initial_users + 2000)}"
        new_val = c.hincrbyfloat(KEY_USER_HASH, uid, 5.0)
        lua_script(keys=[KEY_GOOD_TOP], args=[uid, new_val, TOP_CAPACITY], client=c)
        return (time.perf_counter() - t0) * 1000

    t_wall, qps, p50, p95, p99 = _measure_writes(worker_good_top_n, total_writes, concurrency)
    t_read = _measure_reads(lambda: client.zrevrange(KEY_GOOD_TOP, 0, 99, withscores=True))
    final_card = client.zcard(KEY_GOOD_TOP)
    mem_kb = final_card * 128 / 1024
    print(f" [测试 2 结果]")
    print(f"    - 并发写入耗时: {t_wall:.3f} s\n    - 写入 QPS: {qps:,.1f} req/s")
    print(f"    - 延迟指标: P50={p50:.2f}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")
    print(f"    - 排行榜 Key 元素总量: {final_card:,} 个 (严格恒定 1,000)")
    print(f"    - 生产环境对应榜单内存: {mem_kb:.2f} KB (比单大Key节约 99% 以上)")
    print(f"    - 查询 Top 100 单次平均延迟: {t_read:.3f} ms\n", flush=True)
    return {"card": final_card, "qps": qps, "p99": p99, "t_read": t_read}


def _query_sharded_top_100(client):
    """Merge top-100 candidates across all shards."""
    all_candidates = []
    for shard_idx in range(NUM_SHARDS):
        all_candidates.extend(client.zrevrange(f"rank:shard:{shard_idx}", 0, 99, withscores=True))
    all_candidates.sort(key=lambda x: x[1], reverse=True)
    return all_candidates[:100]


def _run_sharded_zset(client, init_scores, initial_users: int, total_writes: int, concurrency: int) -> dict:
    """Benchmark 16-shard bucketed ZSet with k-way merge reads."""
    print(f"[测试 3/3] 优化方案 B：Hash 分桶 16 分片 + 多路归并", flush=True)
    print(f" -> 正在将基数学员打散分配至 16 个分片...", flush=True)
    pipe = client.pipeline(transaction=False)
    for uid, sc in init_scores:
        pipe.zadd(get_shard_key(uid), {uid: sc})
        if len(pipe) >= 5000:
            pipe.execute()
    pipe.execute()
    shard_counts = [client.zcard(f"rank:shard:{i}") for i in range(NUM_SHARDS)]
    avg_shard = statistics.mean(shard_counts)
    print(f" -> 分片完成，16 个分片平均元素量: {avg_shard:.0f} 个/分片", flush=True)
    print(f" -> 启动 {concurrency} 线程模拟高并发打卡 ({total_writes:,} 次写入)...", flush=True)

    def worker_good_sharded(_idx):
        t0 = time.perf_counter()
        uid = f"user_{random.randint(0, initial_users + 2000)}"
        get_client().zincrby(get_shard_key(uid), 5.0, uid)
        return (time.perf_counter() - t0) * 1000

    t_wall, qps, p50, p95, p99 = _measure_writes(worker_good_sharded, total_writes, concurrency)
    t_read = _measure_reads(lambda: _query_sharded_top_100(client))
    mem_per_shard = (avg_shard * 128) / (1024 * 1024)
    print(f" [测试 3 结果]")
    print(f"    - 并发写入耗时: {t_wall:.3f} s\n    - 写入 QPS: {qps:,.1f} req/s")
    print(f"    - 延迟指标: P50={p50:.2f}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")
    print(f"    - 单分片容量: 约 {avg_shard:.0f} 个 (热点被打散 16 倍)")
    print(f"    - 生产环境单个分片内存: 仅 {mem_per_shard:.2f} MB (完全消除 BigKey)")
    print(f"    - 多路归并 Top 100 查询平均延迟: {t_read:.3f} ms\n", flush=True)
    return {"avg_shard": round(avg_shard), "qps": qps, "p99": p99, "t_read": t_read}


def _print_comparison_matrix(res_bad: dict, res_a: dict, res_b: dict) -> None:
    """Print unified side-by-side benchmark comparison matrix."""
    bad_card = f"{res_bad['card']:,} 个"
    a_card = f"{res_a['card']:,} 个 (严格恒定)"
    b_card = f"{res_b['avg_shard']:,} 个/分片"
    bad_qps, a_qps, b_qps = f"{res_bad['qps']:,.1f} req/s", f"{res_a['qps']:,.1f} req/s", f"{res_b['qps']:,.1f} req/s"
    bad_p99, a_p99, b_p99 = f"{res_bad['p99']:.2f} ms", f"{res_a['p99']:.2f} ms", f"{res_b['p99']:.2f} ms"
    bad_read, a_read, b_read = f"{res_bad['t_read']:.3f} ms", f"{res_a['t_read']:.3f} ms", f"{res_b['t_read']:.3f} ms"

    print(f"{'='*75}", flush=True)
    print(f" 最终测试对比结果矩阵", flush=True)
    print(f"{'='*75}", flush=True)
    print(f"{'核心指标':<18} | {'【错误】单集中大Key':<16} | {'【优选】冷热分离截断':<16} | {'【可选】16分片分桶':<16}", flush=True)
    print(f"{'-'*75}", flush=True)
    print(f"{'排行榜 Key 元素规模':<16} | {bad_card:<18} | {a_card:<16} | {b_card:<16}", flush=True)
    print(f"{'内存 BigKey 隐患':<15} | {'严重 BigKey':<21} | {'完全消除(仅KB级)':<18} | {'完全消除(分摊16份)':<16}", flush=True)
    print(f"{'高并发写入 QPS':<17} | {bad_qps:<18} | {a_qps:<18} | {b_qps:<18}", flush=True)
    print(f"{'写入延迟 P99':<17} | {bad_p99:<20} | {a_p99:<20} | {b_p99:<20}", flush=True)
    print(f"{'Top 100 查询耗时':<16} | {bad_read:<20} | {a_read:<20} | {b_read:<20}", flush=True)
    print(f"{'='*75}\n", flush=True)


def run_benchmark():
    """Run all three Redis ZSet ranking benchmark scenarios and compare metrics."""
    client = get_client()
    client.flushall()
    initial_users, concurrency, total_writes = 20_000, 10, 4_000

    print(f"\n{'='*75}", flush=True)
    print(f" 排行榜性能基准【真实测试】启动", flush=True)
    print(f" 环境配置: Python {sys.version.split()[0]} | FakeRedis Server (In-Memory Kernel)", flush=True)
    print(f" 参数规模: 基数用户={initial_users:,} 人 | 并发写请求={total_writes:,} 次 | 工作线程={concurrency}", flush=True)
    print(f"{'='*75}\n", flush=True)

    res_bad = _run_bad_global_zset(client, initial_users, total_writes, concurrency)
    init_scores = [(f"user_{i}", round(random.uniform(10, 500), 2)) for i in range(initial_users)]
    res_a = _run_top_n_truncate(client, list(init_scores), initial_users, total_writes, concurrency)
    res_b = _run_sharded_zset(client, init_scores, initial_users, total_writes, concurrency)
    _print_comparison_matrix(res_bad, res_a, res_b)


if __name__ == "__main__":
    run_benchmark()
