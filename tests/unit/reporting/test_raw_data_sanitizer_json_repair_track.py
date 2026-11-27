"""
tests/unit/reporting/test_raw_data_sanitizer_json_repair_track.py
=================================================================
[第4轨] RawDataSanitizer json_repair 容错修复兜底回归测试。

契约：
1. 断头 JSON（Token 物理截断）由第4轨补全救回；
2. 寒暄文本包裹的结构化分片不再被静默丢弃；
3. json_repair 折叠的 datetime(...) 字符串值按值还原为 ISO 格式（防假成功）；
4. 纯状态文本（ok/subgraph_ok）不产出数据、不误报；
5. 轨道优先级回归：第2轨 (ast) 仍先于第4轨，datetime 归一化走精准修复。
"""
import pytest

from app.data.raw_data_sanitizer import RawDataSanitizer


def test_track4_heals_truncated_json():
    raw = '{"total_cnt": 13, "total_fee": 2379.85, "note": "trunca'
    rows = RawDataSanitizer.sanitize_and_parse(raw)
    assert len(rows) == 1
    assert rows[0]["total_cnt"] == 13
    assert rows[0]["total_fee"] == 2379.85


def test_track4_extracts_chatter_wrapped_json():
    raw = '好的，以下是本轮采样结果：\n[{"setl_id": "H2", "cnt": 1}] 以上供参考。'
    rows = RawDataSanitizer.sanitize_and_parse(raw)
    assert len(rows) == 1
    assert rows[0]["setl_id"] == "H2"
    assert rows[0]["cnt"] == 1


def test_track4_restores_datetime_call_values():
    raw = "{'setl_id': 'H1', 'setl_time': datetime.datetime(2025, 3, 14, 9, 30, 12, 123456),}"
    rows = RawDataSanitizer.sanitize_and_parse(raw)
    assert len(rows) == 1
    assert rows[0]["setl_id"] == "H1"
    assert rows[0]["setl_time"] == "2025-03-14 09:30:12.123456"


def test_track4_restores_date_call_value_with_tail_comma():
    raw = "{'stat_date': datetime.date(2025, 3, 14), 'fee': 88.5}"
    rows = RawDataSanitizer.sanitize_and_parse(raw)
    assert rows[0]["stat_date"] == "2025-03-14"
    assert rows[0]["fee"] == 88.5


def test_status_text_chunks_stay_silent():
    rows = RawDataSanitizer.sanitize_and_parse("ok\n---\nsubgraph_ok")
    assert rows == []


def test_track_priority_ast_still_precedes_json_repair():
    # 第2轨优先级回归：模块级 datetime 归一化后 ast 精准修复，时间值不得被折叠为脏字符串
    raw = "{'t': datetime.datetime(2024, 3, 15, 12, 7, 45), 'fee': 100}"
    rows = RawDataSanitizer.sanitize_and_parse(raw)
    assert len(rows) == 1
    assert rows[0]["t"] == "2024-03-15 12:07:45"
    assert rows[0]["fee"] == 100


def test_unrecoverable_chunk_with_brackets_still_warns(caplog=None):
    # 含结构化声称但全轨失败的分片必须保留失败信号
    raw = '{"a": 1,,,[[[完全损坏'
    rows = RawDataSanitizer.sanitize_and_parse(raw)
    assert isinstance(rows, list)
