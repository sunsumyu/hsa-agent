# -*- coding: utf-8 -*-
import os, sys, asyncio
sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["DISABLE_AUDIT_CACHE"] = "true"

from app.core.llm_provider import llm_provider
from app.core.registry import skill_registry
from app.core.permission_manager import permission_manager
from app.core.prompts import CODER_PROMPT
from app.infra.neo4j_manager import neo4j_manager

async def test_coder():
    # Setup state mimicking QA-CUST-23
    user_q = "查一下理疗科和康复科的执行大夫。你去按每一分钟去排一下他们做一对一手法治疗的单子，看看有没有哪个大夫练了分身术，在同一时间段里，系统上竟然显示他同时在给五六个病号做必须要医生亲自上手推拿的项目？这种纯粹就是护士拿着卡乱刷、甚至连病号都没来直接挂空床的虚假理疗。"
    methodology = "理疗康复医师时序冲突核查：通过关联结算主表与明细表，筛选物理治疗/手法理疗项目，按医生 chfpdr_name / chfpdr_code 与 fee_ocur_time 分组聚合，筛选出在同一分钟内服务多名不同参保人的异常明细。"
    tasks = "1. 识别并查询出理疗科手法治疗的相关字段；\n2. 编写 SQL 关联 fqz_gz_jzsj_all_ql 与 fqz_fymx_test，按 chfpdr_name 和 fee_ocur_time 统计不同参保人 psn_no 的数量。"

    # 1. Tools
    all_tools = skill_registry.get_all_skills()
    tools = permission_manager.filter_skills("default_admin", all_tools)

    # 2. Schema Registry DDL context
    from app.core.registry.schema_registry import schema_registry
    schema_hint = schema_registry.get_tables_summary()

    # 3. System prompt construction
    scenario_guidelines = (
        "\n\n【⚠️ 物理 CLICKHOUSE SQL 刚性编写红线 - 理疗手法时间冲突核查】\n"
        "1. 任务要求核查理疗科/康复科手法治疗项目的执行时间重叠。你**必须**使用 `disease_code` 或 `item_name` 过滤出理疗、推拿、按摩等手法康复项目（例如 `item_name LIKE '%推拿%' OR item_name LIKE '%手法%' OR item_name LIKE '%按摩%'`）。\n"
        "2. 你**必须**按执行医生/理疗师（`chfpdr_name`）与费用发生时间（`fee_ocur_time`）进行排序和聚合计算，判定物理重合！"
    )
    experiences = f"【已启用 GSSC 统一上下文】{scenario_guidelines}"

    prompt = CODER_PROMPT.format_messages(
        original_question=user_q,
        messages=[("human", user_q)],
        ontology=neo4j_manager.get_ontology(),
        schema_info=schema_hint,
        methodology=methodology,
        tasks=tasks,
        experiences=experiences
    )

    print("Sending prompt to Coder LLM...")
    try:
        response = await llm_provider.chat(
            role="coder",
            messages=prompt,
            tools=tools
        )
        print("\n" + "=" * 80)
        print("CODER RESPONSE")
        print("=" * 80)
        print(f"Content: {response.content}")
        print(f"Tool Calls: {getattr(response, 'tool_calls', None)}")
        print("=" * 80)
    except Exception as e:
        print(f"Error calling LLM: {e}")

if __name__ == "__main__":
    asyncio.run(test_coder())
