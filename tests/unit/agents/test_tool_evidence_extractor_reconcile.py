"""
tests/unit/agents/test_tool_evidence_extractor_reconcile.py
===========================================================
[证据对账] ToolEvidenceExtractor 通道行数计数与 Append-Only 累加回归测试。

契约：
1. evidence_row_count 与 raw_data 使用同一 sanitizer 口径（实际可解析行数）；
2. 多轮 Append-Only 累加：新分片追加时行数累加，去重跳过时不重复累加；
3. 计数与 raw_data 通道内容严格一致（解析无丢失时 parsed == carried）。
"""
import pytest

from app.agents.tool_evidence_extractor import tool_evidence_extractor


def _mk_result(rows):
    """构造与 ToolEngine 返回结构一致的 SUCCESS 结果"""
    return {
        "status": "SUCCESS",
        "sql_logic": "SELECT id, fee FROM fqz_setl WHERE admdvs='420100'",
        "methodology": "测试取证",
        "data": rows,
    }


def _mk_call():
    return {"name": "execute_audit_sql", "id": "call_test_1"}


def test_evidence_row_count_matches_parsed_rows():
    res = _mk_result([{"id": 1, "fee": 100.0}, {"id": 2, "fee": 200.0}, {"id": 3, "fee": 300.0}])
    out = tool_evidence_extractor.process([(_mk_call(), res)], {})
    assert out.evidence_row_count == 3
    assert len(out.raw_data) > 0


def test_evidence_row_count_accumulates_append_only():
    res1 = _mk_result([{"id": 1, "fee": 100.0}, {"id": 2, "fee": 200.0}])
    first = tool_evidence_extractor.process([(_mk_call(), res1)], {})

    # 第二轮: 携带既有证据, 追加新分片
    res2 = _mk_result([{"id": 9, "fee": 900.0}])
    state = {"raw_data": first.raw_data, "evidence_row_count": first.evidence_row_count}
    second = tool_evidence_extractor.process([(_mk_call(), res2)], state)

    assert second.evidence_row_count == first.evidence_row_count + 1
    assert second.raw_data.count("---") >= 1  # Append-Only 拼接


def test_evidence_row_count_not_duplicated_on_chunk_dedup():
    res1 = _mk_result([{"id": 1, "fee": 100.0}])
    first = tool_evidence_extractor.process([(_mk_call(), res1)], {})

    # 同一结果重复提交 (如 critic 重试后原样重跑) → 去重跳过, 行数不得重复累加
    state = {"raw_data": first.raw_data, "evidence_row_count": first.evidence_row_count}
    again = tool_evidence_extractor.process([(_mk_call(), res1)], state)

    assert again.evidence_row_count == first.evidence_row_count


def test_carried_count_equals_sanitizer_parse_output():
    # 口径一致性: extractor 计数 == Reporter 端 sanitize_and_parse 实得行数 (解析无丢失时)
    from app.data.raw_data_sanitizer import RawDataSanitizer

    res = _mk_result([{"id": 1}, {"id": 2}])
    out = tool_evidence_extractor.process([(_mk_call(), res)], {})
    parsed = RawDataSanitizer.sanitize_and_parse(out.raw_data)
    assert out.evidence_row_count == len(parsed)
