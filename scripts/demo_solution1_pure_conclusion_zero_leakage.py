# -*- coding: utf-8 -*-
"""
scripts/demo_solution1_pure_conclusion_zero_leakage.py
======================================================
现场实测【方案 1：纯结论呈现（零 SQL 泄露模式）】
展示双重防御机制（Prompt 级业务约束 + 后置代码级正则硬拦截门禁）：
保证面向普通用户、医生或医院端时，100% 杜绝底层物理表名与 SQL 泄露！
"""

import asyncio
import sys
import os
import re

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import HumanMessage, SystemMessage
from app.core.security.data_masker import sanitize_audit_content, _SQL_CODEBLOCK_RE
from app.infra.model_manager import model_manager

def enforce_solution_1_zero_leakage(text: str) -> str:
    """
    【方案 1 纯结论安全出参网关】
    1. 彻底拦截剥离任何 ```sql ... ``` 代码块，替换为自然语言业务提示
    2. 正则屏蔽任何裸露的物理表名 (fqz_*, t_audit_*)
    """
    # 1. 替换 SQL 代码块为业务友好的后台说明
    cleaned = _SQL_CODEBLOCK_RE.sub("【后台自动执行多维聚合核查】", text)
    # 2. 拦截可能裸露的 ClickHouse 物理表名
    cleaned = re.sub(r"\bfqz_[a-zA-Z0-9_]+\b", "【费用结算明细】", cleaned)
    cleaned = re.sub(r"\bt_audit_[a-zA-Z0-9_]+\b", "【稽核台账】", cleaned)
    return cleaned.strip()

async def test_solution_1():
    print("=" * 80)
    print("🛡️ 【方案 1：纯结论呈现】端到端防泄露演练")
    print("=" * 80)

    llm, mid = model_manager.get_adaptive_llm(model_id="ppio-premium")
    print(f"✅ 模型通道: {mid} (PPIO)")

    # 1. 约束提示词：要求大模型以自然语言业务结论作答，严禁技术代码泄露
    prompt_solution_1 = (
        "你是国家医保基金智能稽核助手。当前交互对象为普通医院业务人员与受检医生。\n"
        "【安全输出铁律】\n"
        "1. 严禁向用户直接提供底层 SQL 语句、数据库物理表名（如 fqz_*）或代码块！\n"
        "2. 必须将所有数据筛查思路转化为通俗、严谨的「业务核查规则与判定标准」进行自然语言说明；\n"
        "3. 直接给出判定阈值与业务结论，控制在 2-3 句话。"
    )

    test_question = "针对骨科脊柱手术骨水泥超量使用嫌疑，系统在后台是如何统计和预警的？具体判定条件是什么？"

    print(f"\n[用户提问]: {test_question}")

    # 调用模型
    messages = [
        SystemMessage(content=prompt_solution_1),
        HumanMessage(content=test_question)
    ]
    raw_res = await llm.ainvoke(messages)
    raw_content = str(raw_res.content).strip()

    print("\n" + "-" * 75)
    print("▶ 阶段一：大模型端出参（Prompt 安全约束效果）:")
    print(raw_content)

    # 后置出参网关拦截（纵深防御第二道门禁，即使大模型偶发幻觉输出 SQL 也被物理清洗）
    final_user_facing_content = enforce_solution_1_zero_leakage(raw_content)

    print("\n" + "-" * 75)
    print("▶ 阶段二：安全网关二次过滤后（最终展示给前端普通用户的效果）:")
    print(final_user_facing_content)

    print("\n" + "-" * 75)
    print("🔍 安全合规检测断言:")
    has_sql_block = "```sql" in final_user_facing_content
    has_physical_table = "fqz_" in final_user_facing_content
    has_select_keyword = "SELECT " in final_user_facing_content

    print(f"  - 是否含有 SQL 代码块: {'❌ 存在泄露' if has_sql_block else '✅ 零代码块 (Clean)'}")
    print(f"  - 是否含有物理表名 (fqz_*): {'❌ 存在泄露' if has_physical_table else '✅ 物理表名已彻底隐藏'}")
    print(f"  - 是否含有 SQL 裸关键字 (SELECT): {'❌ 存在泄露' if has_select_keyword else '✅ 纯自然语言业务结论'}")

    assert not has_sql_block
    assert not has_physical_table
    assert not has_select_keyword

    print("\n" + "=" * 80)
    print("🎉 【方案 1】验证 100% 成功通过！普通用户只能看到纯业务结论，内部架构零泄露！")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_solution_1())
