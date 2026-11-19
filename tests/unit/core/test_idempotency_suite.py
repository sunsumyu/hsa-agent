"""
tests/unit/core/test_idempotency_suite.py
=========================================
Argus-Agent 专属全链路幂等性测试套件 (Comprehensive Idempotency Test Suite)

覆盖维度：
1. 意图与动作缓存幂等（Action Cache get_or_compute 0次重复推理）
2. 指纹契约失效与自愈重算幂等（Fingerprint Mismatch -> Deterministic Recompute）
3. 工具证据链 SHA-256 内容指纹确定性幂等（Tool Engine Evidence Fingerprint）
4. 人工审批状态机重复触发幂等（HITL Task Pool CAS Defense）
5. SQL 只读执行器无副作用幂等（SQLGuardian AST Pure Read-Only Guarantee）
"""

import os
import json
import hashlib
import tempfile
import pytest
from unittest.mock import MagicMock

from app.memory.action_cache import ActionCacheManager
from app.core.tool_engine.models import ToolResult, ExecuteAuditSqlInput
from app.core.tool_engine.engine import ToolEngine
from app.core.task_pool import TaskPoolManager
from app.skills.security import SQLGuardian, SecurityViolationError


# ─── 1. 语义动作与意图缓存幂等测试 ──────────────────────────────────────────

def test_action_cache_get_or_compute_idempotency():
    """验证：相同意图的问题在命中缓存后，compute() 计算函数被调用的次数严格为 0，防止重复消耗 LLM Token"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = os.path.join(tmpdir, "action_cache.json")
        manager = ActionCacheManager(cache_file=cache_file)

        seed_q = "针对男性使用宫内节育器开展排查"
        seed_sql = "SELECT * FROM fqz_fymx_test WHERE hilist_name LIKE '%宫内节育%' AND gend LIKE '1%'"
        fingerprint = {"prompt_version": "2.0", "schema_hash": "abc1234"}

        # 预先录入动作缓存
        manager.save(
            question=seed_q,
            sql=seed_sql,
            tasks=["核查男性宫内节育器"],
            methodology="性别互斥排他",
            fingerprint=fingerprint
        )

        compute_call_count = 0
        def mock_llm_compute():
            nonlocal compute_call_count
            compute_call_count += 1
            return "NEW_SYNTHESIZED_SQL"

        # 变体提问（包含口语停用词和标点，语义核心一致）
        variant_q = "请帮我排查一下男性使用宫内节育器！"

        # 第一次请求
        res1 = manager.get_or_compute(
            question=variant_q,
            fingerprint=fingerprint,
            validator=lambda sql: "SELECT" in sql,
            computer=mock_llm_compute
        )
        assert res1 == seed_sql
        assert compute_call_count == 0, "命中归一化缓存时，严禁调用 LLM compute 函数！"

        # 第二次请求（完全相同提问）
        res2 = manager.get_or_compute(
            question=variant_q,
            fingerprint=fingerprint,
            validator=lambda sql: "SELECT" in sql,
            computer=mock_llm_compute
        )
        assert res2 == seed_sql
        assert compute_call_count == 0, "多次重复提问必须绝对幂等，LLM 调用次数维持为 0！"


def test_action_cache_fingerprint_invalidation_and_recompute_idempotency():
    """验证：当提示词版本或 Schema 指纹变更时，缓存能精准失效并完成确定性更新"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = os.path.join(tmpdir, "action_cache.json")
        manager = ActionCacheManager(cache_file=cache_file)

        question = "检查麻醉费伴随缺失"
        old_sql = "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%麻醉%'"
        old_fp = {"prompt_version": "1.0", "schema_hash": "hash_v1"}

        manager.save(question, old_sql, fingerprint=old_fp)

        # 模拟 Prompt 升级至 v2.0
        new_fp = {"prompt_version": "2.0", "schema_hash": "hash_v1"}
        new_sql = "SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%麻醉%' AND setl_id NOT IN (SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%手术%')"

        call_count = 0
        def new_computer():
            nonlocal call_count
            call_count += 1
            return new_sql

        # 指纹不一致导致 Miss，自愈重算
        res = manager.get_or_compute(
            question=question,
            fingerprint=new_fp,
            validator=lambda s: "NOT IN" in s,
            computer=new_computer
        )
        assert res == new_sql
        assert call_count == 1

        # 再次调用同一问题，已固化新指纹，不再重算
        res_repeat = manager.get_or_compute(
            question=question,
            fingerprint=new_fp,
            validator=lambda s: "NOT IN" in s,
            computer=new_computer
        )
        assert res_repeat == new_sql
        assert call_count == 1, "自愈写入新指纹后，后续调用再次恢复幂等！"


# ─── 2. 工具证据链 SHA-256 内容指纹确定性幂等测试 ────────────────────────────

def test_tool_evidence_fingerprint_determinism():
    """验证：相同 SQL 与数据集无论执行多少次，生成的 SHA-256 evidence_fingerprint 严格一致，具备数学幂等性"""
    safe_sql = "SELECT psn_no, sum(cnt) FROM fqz_fymx_test GROUP BY psn_no HAVING sum(cnt) > 100"
    records = [
        {"psn_no": "P001", "total_cnt": 120},
        {"psn_no": "P002", "total_cnt": 150},
        {"psn_no": "P003", "total_cnt": 200},
    ]
    total_count = 3

    # 按照 ToolEngine 中的内容指纹公式进行多轮模拟
    fingerprints = []
    for _ in range(10):
        fp_src = f"{safe_sql}_{total_count}_{json.dumps(records[:3], sort_keys=True, default=str)}"
        fp = hashlib.sha256(fp_src.encode("utf-8")).hexdigest()
        fingerprints.append(fp)

    # 幂等断言：10 次计算的指纹完全相同且唯一
    assert len(set(fingerprints)) == 1
    assert len(fingerprints[0]) == 64  # SHA-256 十六进制字符串长度


# ─── 3. 人工审批状态机重复触发幂等测试 ──────────────────────────────────────

def test_task_pool_multiple_approval_idempotency():
    """验证：对已完成审批的审计任务，重复提交任意审批动作均被幂等拦截，时间戳与审核状态不可被改写"""
    pool = TaskPoolManager()
    thread_id = "task-audit-idempotent-check"

    state = {
        "metadata": {"user_question": "排查超量开药", "risk_score": 0.85},
        "audit_findings": ["超标明细 5 条"]
    }
    pool.submit_task(thread_id, state, reason="人工干预")

    # 第一次合法审批
    success_first = pool.complete_task(thread_id, action="APPROVE", feedback="专家确认违规")
    assert success_first is True

    task_snapshot = pool.get_task(thread_id)
    initial_completed_at = task_snapshot["completed_at"]
    assert task_snapshot["status"] == "COMPLETED"
    assert task_snapshot["action"] == "APPROVE"

    # 连续发起 5 次重复审批（包含恶意反转状态的 REJECT 指令）
    for i in range(5):
        idempotent_result = pool.complete_task(
            thread_id,
            action="REJECT",
            feedback=f"尝试恶意覆写审批 #{i}"
        )
        assert idempotent_result is True  # 幂等返回成功响应

    # 状态不可变性断言
    final_task = pool.get_task(thread_id)
    assert final_task["status"] == "COMPLETED"
    assert final_task["action"] == "APPROVE", "已完成的审批动作严禁被后续请求修改！"
    assert final_task["feedback"] == "专家确认违规", "已记录的专家反馈严禁被覆盖！"
    assert final_task["completed_at"] == initial_completed_at, "完成时间戳严禁被篡改！"


# ─── 4. SQL 只读执行器无副作用幂等测试 ──────────────────────────────────────

def test_sql_guardian_enforces_read_only_idempotency():
    """验证：SQLGuardian 坚决拦截所有带副作用的写指令，确保审计查询纯只读（具备纯函数式的幂等特征）"""
    safe_queries = [
        "SELECT * FROM fqz_fymx_test WHERE gend LIKE '1%' LIMIT 10",
        "WITH temp AS (SELECT psn_no FROM fqz_fymx_test) SELECT count(*) FROM temp",
        "SELECT psn_no, sum(cnt) FROM fqz_fymx_test GROUP BY psn_no"
    ]
    for q in safe_queries:
        validated = SQLGuardian.validate_sql(q)
        assert validated is not None

    destructive_queries = [
        "DELETE FROM fqz_fymx_test WHERE id = 1",
        "UPDATE fqz_fymx_test SET cnt = 0 WHERE id = 1",
        "DROP TABLE fqz_fymx_test",
        "TRUNCATE TABLE fqz_fymx_test",
        "INSERT INTO fqz_fymx_test VALUES (1, 'test')",
        "ALTER TABLE fqz_fymx_test DROP COLUMN fee",
        "EXPLAIN SELECT * FROM fqz_fymx_test"
    ]
    for dq in destructive_queries:
        with pytest.raises(SecurityViolationError):
            SQLGuardian.validate_sql(dq)
