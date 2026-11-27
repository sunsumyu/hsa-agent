# -*- coding: utf-8 -*-
"""
TDD Suite 2: Query Projection & Safe Evidence Slicing Tests
============================================================
Driven by: docs/SPEC_DETERMINISTIC_CACHE_AND_SCHEMA_SEAMS.md
Testing Seam: ToolEvidenceExtractor & ReportRenderer Data Coercion

断言目标:
1. 传入数万字符的超大字典列表，提取器必须在结构化对象级别切片，返回的 JSON 必须 100% 可解析，绝不能产生 unterminated string literal 破坏；
2. report_renderer 解析由安全切片提取的结果时，严禁抛错崩溃回退为 0 条。
"""
import pytest
import json
from app.reporting.report_renderer import report_renderer


class TestQueryProjectionAndEvidenceSlicing:
    """验证结果集安全结构化切片与合法 JSON 序列化"""

    def test_large_record_set_slicing_never_corrupts_json_syntax(self):
        """
        [红灯测试 3] 超大结果集安全切片：
        构造包含 1000 条真实长字典的数据集（总字符超 100,000 字符）。
        测试系统在提取证据或切片时，绝不能在字符串任意字节硬切，导致 JSON 损坏。
        """
        # 构造大型数据集（模拟费用明细宽表）
        large_dataset = [
            {
                "psn_no": f"PSN_NO_LONG_HASH_{i:06d}_DEEP_TESTING_DATA",
                "fixmedins_name": f"某市某定点零售药店与中西医结合诊所分部_{i}",
                "gend": "1",
                "hilist_name": f"地屈孕酮片及益母草颗粒妇科专属药品包装规格规格说明_{i}",
                "det_item_fee_sumamt": 45.8 + i
            }
            for i in range(1000)
        ]

        raw_json_str = json.dumps(large_dataset, ensure_ascii=False)
        assert len(raw_json_str) > 80000, "测试数据集应足够大以触发截断防护"

        # 使用 report_renderer.clean_and_parse_raw_data 解析
        parsed_rows = report_renderer.clean_and_parse_raw_data(raw_json_str)

        # 断言解析绝不能因截断而返回空列表
        assert isinstance(parsed_rows, list)
        assert len(parsed_rows) > 0, "大结果集被截断损坏导致解析结果回退为 0 条！"
        # 且第一条数据的字段必须完整无损
        assert "psn_no" in parsed_rows[0]
        assert "det_item_fee_sumamt" in parsed_rows[0]

    def test_broken_truncated_string_is_gracefully_healed_or_rejected(self):
        """
        [红灯测试 4] 恶意模拟被暴力切断的残缺字符串：
        例如 tool_evidence_extractor 在中途硬切断：'[{"psn_no": "123", "name": "测'
        系统必须能够防御性恢复或优雅处理，绝不能导致下游崩溃回退。
        """
        corrupted_raw_data = '[{"psn_no": "123", "name": "测试机构"}, {"psn_no": "456", "name": "截断在这'
        
        # 运行解析方法
        parsed = report_renderer.clean_and_parse_raw_data(corrupted_raw_data)
        
        # 至少应当提取出前一条完整完备的有效记录，而不是因为第二条残缺就让整批数据全部作废清零！
        assert len(parsed) >= 1, "残缺切片导致有效数据被全部丢弃！"
        assert parsed[0]["psn_no"] == "123"
