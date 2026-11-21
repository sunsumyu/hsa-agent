"""
tests/unit/data/test_raw_data_sanitizer_boundary_red.py
======================================================
测试驱动开发 (TDD) 红灯测试:
验证 RawDataSanitizer.extract_scan_boundary 物理探针基数与时空范围提取能力
"""

import pytest
from app.data.raw_data_sanitizer import RawDataSanitizer


def test_extract_scan_boundary_empty():
    assert RawDataSanitizer.extract_scan_boundary(None) == (None, None, None)
    assert RawDataSanitizer.extract_scan_boundary("") == (None, None, None)
    assert RawDataSanitizer.extract_scan_boundary("   ") == (None, None, None)


def test_extract_scan_boundary_json_standard():
    raw_str = '[{"total_cnt": 1250, "min_time": "2024-01-01 08:00:00", "max_time": "2024-06-30 23:59:59"}]'
    total_cnt, min_t, max_t = RawDataSanitizer.extract_scan_boundary(raw_str)
    assert total_cnt == 1250
    assert min_t == "2024-01-01"
    assert max_t == "2024-06-30"


def test_extract_scan_boundary_aliases_and_iso():
    # 测试 count(*), min(setl_time), ISO 8601 日期时间带 T
    raw_str = '[{"count(*)": "8848", "min(setl_time)": "2023-12-01T10:20:30.000", "max(setl_time)": "2024-03-15T18:00:00"}]'
    total_cnt, min_t, max_t = RawDataSanitizer.extract_scan_boundary(raw_str)
    assert total_cnt == 8848
    assert min_t == "2023-12-01"
    assert max_t == "2024-03-15"


def test_extract_scan_boundary_multitrack_with_dirty_chars():
    # 测试多分片 --- 与控制字符
    raw_str = (
        "\x00\x08--- \n"
        "[{\"cnt\": 500, \"min_t\": \"2024-05-01\"}] \n"
        "--- \n"
        "[{\"max_t\": \"2024-05-31 12:00:00.123\"}]"
    )
    total_cnt, min_t, max_t = RawDataSanitizer.extract_scan_boundary(raw_str)
    assert total_cnt == 500
    assert min_t == "2024-05-01"
    assert max_t == "2024-05-31"


def test_extract_scan_boundary_invalid_data():
    # 畸形字符串不崩溃，安全返回 (None, None, None)
    raw_str = "Invalid SQL error text with no structure"
    assert RawDataSanitizer.extract_scan_boundary(raw_str) == (None, None, None)
