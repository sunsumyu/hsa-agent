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
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

async def run_react():
    user_q = "查一下理疗科和康复科的执行大夫。你去按每一分钟去排一下他们做一对一手法治疗的单子，看看有没有哪个大夫练了分身术，在同一时间段里，系统上竟然显示他同时在给五六个病号做必须要医生亲自上手推拿的项目？这种纯粹就是护士拿着卡乱刷、甚至连病号都没来直接挂空床的虚假理疗。"
    methodology = "理疗康复医师时序冲突核查：通过关联结算主表与明细表，筛选物理治疗/手法理疗项目，按医生 chfpdr_name / chfpdr_code 与 fee_ocur_time 分组聚合，筛选出在同一分钟内服务多名不同参保人的异常明细。"
    tasks = "1. 识别并查询出理疗科手法治疗的相关字段；\n2. 编写 SQL 关联 fqz_gz_jzsj_all_ql 与 fqz_fymx_test，按 chfpdr_name 和 fee_ocur_time 统计不同参保人 psn_no 的数量。"

    # 1. Tools
    all_tools = skill_registry.get_all_skills()
    tools = permission_manager.filter_skills("default_admin", all_tools)

    # 2. Schema Registry DDL context
    from app.core.registry.schema_registry import schema_registry
    schema_hint = schema_registry.get_tables_summary()

    # 3. Scenario SQL Guidelines
    scenario_guidelines = (
        "\n\n【⚠️ 物理 CLICKHOUSE SQL 刚性编写红线 - 理疗手法时间冲突核查】\n"
        "1. 你**必须**将结算主表 `fqz_gz_jzsj_all_ql` 与费用明细表 `fqz_fymx_test` 按照 `setl_id` 进行关联 (JOIN)。\n"
        "2. 你**必须**使用明细表中的 `hilist_name` 过滤出手法康复项目（例如 `hilist_name LIKE '%推拿%' OR hilist_name LIKE '%手法%' OR hilist_name LIKE '%按摩%'`）。\n"
        "3. 你**必须**以主表中的执行医生（`chfpdr_name` 或 `chfpdr_code`）与明细表中的费用执行时间（`fee_ocur_time`）进行排序或聚合分析，统计同一医生在同一分钟/时间段内为多位不同患者（`feelist_psn_no` 或 `psn_no`）做一对一手法治疗的重叠记录，判定物理重合违规！"
    )
    experiences = f"【已启用 GSSC 统一上下文】{scenario_guidelines}"

    # First turn message history
    messages_history = [HumanMessage(content=user_q)]

    for turn in range(1, 6):
        prompt = CODER_PROMPT.format_messages(
            original_question=user_q,
            messages=messages_history,
            ontology=neo4j_manager.get_ontology(),
            schema_info=schema_hint,
            methodology=methodology,
            tasks=tasks,
            experiences=experiences
        )

        print(f"\n--- TURN {turn}: Calling Coder LLM ---")
        response = await llm_provider.chat(
            role="coder",
            messages=prompt,
            tools=tools
        )
        print(f"Turn {turn} AIMessage Content: {response.content}")
        print(f"Turn {turn} Tool Calls: {getattr(response, 'tool_calls', None)}")

        if not getattr(response, "tool_calls", None):
            print(f"No tool calls in Turn {turn}. Coder completed its execution!")
            break

        # Execute tools
        tool_msgs = []
        for tc in response.tool_calls:
            t_instance = next((t for t in tools if t.name == tc["name"]), None)
            if t_instance:
                print(f"Executing tool {tc['name']} with args {tc['args']}...")
                args = tc["args"].copy() if isinstance(tc["args"], dict) else {}
                if tc["name"] == "execute_audit_sql":
                    args["state"] = {
                        "messages": messages_history,
                        "metadata": {
                            "tenant_id": "test_tenant",
                            "admin_division": "310000"
                        }
                    }
                res = await t_instance.ainvoke(args)
                # Slicing like coder_agent
                tool_msg = ToolMessage(content=str(res)[:2000], tool_call_id=tc["id"])
                tool_msgs.append(tool_msg)
            else:
                print(f"Tool {tc['name']} not found!")

        # Append response and tool messages to history
        messages_history.append(response)
        messages_history.extend(tool_msgs)

if __name__ == "__main__":
    asyncio.run(run_react())
