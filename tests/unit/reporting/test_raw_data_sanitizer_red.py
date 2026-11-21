"""
[Martin Fowler TDD - 红灯测试 (Red Test)]
测试目标：将隐匿在 report_renderer.py 中的 100+ 行数据清洗与反序列化逻辑，
抽取为独立的深模块 RawDataSanitizer (app.data.raw_data_sanitizer)。

Matt Pocock 设计契约：
1. 职责分离 (Locality)：报告渲染器只管渲染 Markdown，数据去污/多轨解析归属于数据清洗深模块。
2. 极简 Interface：仅开放唯一的核心契约 sanitize_and_parse(raw_data_str: Any) -> List[Dict[str, Any]]
3. 内部消化控制字符过滤、datetime repr 转义、多分片 --- 聚合、损坏 JSON 防御性自愈。
"""
import pytest

def test_raw_data_sanitizer_deep_module_exists_and_parses():
    # 尝试从预期的新深模块中导入 (当前尚未创建，预期 RED 报错)
    from app.data.raw_data_sanitizer import RawDataSanitizer
    
    raw_str = '[{"psn_no": "123456", "medfee": 99.5}]'
    result = RawDataSanitizer.sanitize_and_parse(raw_str)
    
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["psn_no"] == "123456"
    assert result[0]["medfee"] == 99.5

def test_raw_data_sanitizer_heals_datetime_and_chunks():
    from app.data.raw_data_sanitizer import RawDataSanitizer
    
    # 包含 datetime.datetime repr 和多分片 ---
    corrupted = (
        '{"time": datetime.datetime(2024, 3, 15, 12, 7, 45), "fee": 100}\n'
        '---\n'
        '{"time": datetime.date(2024, 3, 16), "fee": 200}'
    )
    result = RawDataSanitizer.sanitize_and_parse(corrupted)
    
    assert len(result) == 2
    assert "2024-03-15" in result[0]["time"]
    assert "2024-03-16" in result[1]["time"]


def test_heals_datetime_with_microseconds():
    # 生产日志中 16 次 ast.Call 失败的根因形态之一：微秒第 7 参数
    from app.data.raw_data_sanitizer import RawDataSanitizer

    corrupted = '{"t": datetime.datetime(2024, 3, 15, 12, 7, 45, 123456)}'
    result = RawDataSanitizer.sanitize_and_parse(corrupted)
    assert len(result) == 1
    assert result[0]["t"] == "2024-03-15 12:07:45.123456"


def test_heals_datetime_with_flat_tzinfo_tail():
    # 根因形态之二：扁平 tzinfo 装饰尾参
    from app.data.raw_data_sanitizer import RawDataSanitizer

    corrupted = "{'t': datetime.datetime(2024, 3, 15, 12, 7, 45, tzinfo=timezone.utc), 'fee': 1}"
    result = RawDataSanitizer.sanitize_and_parse(corrupted)
    assert len(result) == 1
    assert result[0]["t"] == "2024-03-15 12:07:45"
    assert result[0]["fee"] == 1


def test_nested_paren_tzinfo_falls_back_without_losing_row():
    # 边界：嵌套括号尾参（timezone(timedelta(hours=8))）不做文本级重写（防跨括号误吞），
    # 行数据经第4轨兜底救回，数值字段完整，时间值保留原始形态（不崩溃、不丢行）
    from app.data.raw_data_sanitizer import RawDataSanitizer

    corrupted = "{'t': datetime.datetime(2024, 3, 15, 12, 7, 45, tzinfo=timezone(timedelta(hours=8)))}"
    result = RawDataSanitizer.sanitize_and_parse(corrupted)
    assert len(result) == 1
    assert "t" in result[0]
