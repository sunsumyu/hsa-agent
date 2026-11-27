"""
Red unit tests for audit_note_store deep module.
"""

import os
import logging
import datetime
import threading
import pytest
from app.skills.federated.audit_note_store import (
    write_note,
    append_entry,
    read_recent_notes,
    read_lines,
    read_raw_text,
    read_notes_with_decay,
    clear_notes,
    format_notes_envelope,
    audit_note_store,
)


@pytest.fixture
def temp_note_file(tmp_path):
    note_file = str(tmp_path / "test_audit_notes.md")
    yield note_file
    if os.path.exists(note_file):
        try:
            os.remove(note_file)
        except OSError as exc:
            logging.getLogger(__name__).debug("cleanup temp note skipped: %s", exc)


class TestAuditNoteStore:
    def test_write_and_read_fresh_note(self, temp_note_file):
        success = write_note("risk_finding", "测试未过期线索", ttl_days=30, file_path=temp_note_file)
        assert success is True
        assert os.path.exists(temp_note_file)

        content = read_notes_with_decay(file_path=temp_note_file)
        assert "RISK_FINDING" in content
        assert "测试未过期线索" in content
        assert "[⏰已过期·仅供参考]" not in content

    def test_read_expired_note_with_ttl(self, temp_note_file):
        write_note("todo", "过期待办事项", ttl_days=1, file_path=temp_note_file)

        future = datetime.datetime.now() + datetime.timedelta(days=5)
        content = read_notes_with_decay(file_path=temp_note_file, now=future)
        assert "[⏰已过期·仅供参考]" in content
        assert "过期待办事项" in content

    def test_clear_notes(self, temp_note_file):
        write_note("blocker", "阻塞项", ttl_days=10, file_path=temp_note_file)
        assert os.path.exists(temp_note_file)
        clear_res = clear_notes(file_path=temp_note_file)
        assert clear_res is True
        assert not os.path.exists(temp_note_file)

    def test_format_notes_envelope(self):
        env = format_notes_envelope("核心便签内容")
        assert env == "<external_audit_notes>\n核心便签内容\n</external_audit_notes>"

    def test_append_entry_and_read_recent_notes(self, temp_note_file):
        for i in range(5):
            append_entry(f"【重点线索】线索_{i}", file_path=temp_note_file)

        recent = read_recent_notes(limit=3, file_path=temp_note_file)
        assert len(recent) == 3
        assert "线索_4" in recent[-1]
        assert "线索_3" in recent[-2]
        assert "线索_2" in recent[-3]

    def test_read_lines_and_read_raw_text(self, temp_note_file):
        append_entry("Line A", file_path=temp_note_file)
        append_entry("Line B", file_path=temp_note_file)

        lines = read_lines(file_path=temp_note_file)
        assert any("Line A" in l for l in lines)
        assert any("Line B" in l for l in lines)

        raw = read_raw_text(file_path=temp_note_file)
        assert "Line A" in raw
        assert "Line B" in raw

    def test_thread_safe_concurrent_appends(self, temp_note_file):
        threads = []
        n_threads = 10

        def worker(idx):
            for j in range(5):
                append_entry(f"Thread_{idx}_Item_{j}", file_path=temp_note_file)

        for i in range(n_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        raw = read_raw_text(file_path=temp_note_file)
        # 10 * 5 = 50 项全部写入，无异常损坏
        for i in range(n_threads):
            for j in range(5):
                assert f"Thread_{i}_Item_{j}" in raw

    def test_read_relevant_notes_prioritizes_blocker_and_query_and_skips_expired(self, temp_note_file):
        # 1. 写入早期 BLOCKER（不应被后续普通便签挤出）
        write_note("blocker", "医保统筹区编码字段缺失", ttl_days=30, file_path=temp_note_file)
        # 2. 写入一条过期的普通便签
        write_note("todo", "已过期的旧待办", ttl_days=1, file_path=temp_note_file)
        # 3. 写入多条较新的普通便签
        write_note("sql_evidence", "分解住院按就诊流水聚合统计", ttl_days=30, file_path=temp_note_file)
        write_note("todo", "核对门诊慢特病机构列表", ttl_days=30, file_path=temp_note_file)
        write_note("todo", "检查退费流水负数金额", ttl_days=30, file_path=temp_note_file)

        future = datetime.datetime.now() + datetime.timedelta(days=3)
        selected = audit_note_store.read_relevant_notes(
            query="分解住院",
            limit=2,
            file_path=temp_note_file,
            now=future,
        )

        assert len(selected) == 2
        assert any("BLOCKER" in s and "医保统筹区编码字段缺失" in s for s in selected)
        assert any("分解住院" in s for s in selected)
        assert all("已过期的旧待办" not in s for s in selected)

    def test_contextvar_session_isolation(self, tmp_path):
        from app.core.context import tenant_context, trace_context
        from app.skills.federated.audit_note_store import AuditNoteStore

        store = AuditNoteStore(default_path=str(tmp_path / "audit_notes.md"))

        t1 = tenant_context.set("tenant_a")
        tr1 = trace_context.set("trace_1")
        try:
            store.write_note("risk_finding", "租户A专属线索")
            notes_a = store.read_relevant_notes(query="租户A")
            assert len(notes_a) == 1
            assert "租户A专属线索" in notes_a[0]
        finally:
            trace_context.reset(tr1)
            tenant_context.reset(t1)

        t2 = tenant_context.set("tenant_b")
        tr2 = trace_context.set("trace_2")
        try:
            assert store.read_relevant_notes(query="租户A") == []
            store.write_note("blocker", "租户B阻塞项")
            notes_b = store.read_relevant_notes()
            assert len(notes_b) == 1
            assert "租户B阻塞项" in notes_b[0]
        finally:
            trace_context.reset(tr2)
            tenant_context.reset(t2)

