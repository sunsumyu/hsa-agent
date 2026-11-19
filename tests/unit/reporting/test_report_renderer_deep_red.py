"""
tests/unit/reporting/test_report_renderer_deep_red.py
====================================================
[TDD Red -> Green] 报告终审与结论 Prompt 构造解耦测试：
1. ConclusionPromptBuilder 针对三种业务边界 (受限执行/零发现防守/正向命中) 的提示词构造
2. AuditReportRenderer 六章节标准化拼装测试
3. 敏感字段物理脱敏与边界透明度验证
"""

import pytest
from app.reporting.conclusion_prompt_builder import build_conclusion_prompt
from app.reporting.report_renderer import AuditReportRenderer, RenderedReport


def test_build_conclusion_prompt_restricted():
    """验证受限执行模式下的 Fail-Closed 提示词防御指引"""
    prompt = build_conclusion_prompt(
        user_question="排查过度诊疗",
        methodology="按频次统计",
        execution_trace=["步骤1: 连接失败"],
        hard_count=0,
        hard_sum=0.0,
        is_restricted=True,
    )
    assert "Fail-Closed" in prompt
    assert "严禁推断业务合规" in prompt
    assert "【执行受限】" in prompt


def test_build_conclusion_prompt_zero_findings():
    """验证零检出情况下的全量扫描基数与违规命中区分说明"""
    prompt = build_conclusion_prompt(
        user_question="排查超量开药",
        methodology="按处方量筛选",
        execution_trace=["步骤1: 全量扫描完成"],
        hard_count=0,
        hard_sum=0.0,
        is_restricted=False,
    )
    assert "时序防守深度" in prompt
    assert "违规异常明细记录为 0 条" in prompt


def test_build_conclusion_prompt_positive_findings():
    """验证正向检出情况下的事实强制对齐指引"""
    prompt = build_conclusion_prompt(
        user_question="排查男性做妇科检查",
        methodology="性别与诊疗项目交叉核验",
        execution_trace=["步骤1: 关联 fqz_fymx_test"],
        hard_count=5,
        hard_sum=12500.0,
        is_restricted=False,
    )
    assert "事实强制对齐" in prompt
    assert "当前发现 5 条记录" in prompt
    assert "12,500.00" in prompt


def test_report_renderer_six_chapters_assembly():
    """验证 AuditReportRenderer 的六章节标准产出"""
    renderer = AuditReportRenderer()
    raw_data = [
        {"psn_no": "P001", "psn_name": "张三", "phone": "13800000000", "medfee_sumamt": 2500.0}
    ]
    report = renderer.render(
        user_question="排查男性结算妇科药品",
        llm_conclusion="经排查发现 1 例男性患者违规结算妇科专属药品。",
        raw_data=raw_data,
        sql_query="SELECT * FROM fqz_fymx_test WHERE gend = '1'",
        table_info="费用明细表",
        total_amount=2500.0,
        finding_count=1,
        audit_metadata={"trace_id": "TR-12345", "model_id": "qwen-max"},
    )
    assert isinstance(report, RenderedReport)
    md = report.markdown
    assert "## 一、审计任务" in md
    assert "## 二、核查口径" in md
    assert "## 三、核查数据发现" in md
    assert "## 四、核查结论" in md
    assert "## 五、风险评级" in md
    assert "## 六、审计可追溯性凭证" in md
    # 敏感字段必须被脱敏或过滤
    assert "13800000000" not in md
    assert "张三" not in md
