import asyncio
import os
import time
from typing import List
from app.agents.agent import get_executor, get_prompt
from app.tools import execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from app.infra.model_manager import model_manager
from dotenv import load_dotenv

load_dotenv(override=True)

def create_agent(model_id, use_palace):
    llm, _ = model_manager.get_adaptive_llm(model_id=model_id, require_tools=True)
    if use_palace:
        tools = [execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge]
    else:
        # 移除检索相关的工具
        tools = [execute_audit_sql, list_tables, calculator]
    agent = create_openai_tools_agent(llm, tools, get_prompt())
    return AgentExecutor(agent=agent, tools=tools, verbose=False)

async def run_comparison():
    model_id = "gemma-4-31b-it" 
    cases = [
        "分析患者 P99999 在 2026 年 1 月 15 日前后的就医行为是否存在异常？",
        "查询最近一年内，总医疗费用排名前三的定点医疗机构。"
    ]
    
    print("# 记忆宫殿 (Memory Palace) 效效对比测试\n")
    print(f"测试模型: {model_id}\n")
    print("| 编号 | 稽核问题 | 模式 | 核心发现 | 政策依据 | 结果判定 |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")

    for i, q in enumerate(cases):
        for mode in ["With-Palace", "No-Palace"]:
            use_palace = (mode == "With-Palace")
            agent_exec = create_agent(model_id, use_palace)
            
            try:
                res = await agent_exec.ainvoke({"input": q, "chat_history": []})
                output = res["output"]
                
                # 简单启发式判定
                has_policy = "政策依据" in output and "规定" in output or "根据" in output
                has_data = "元" in output or "医院" in output
                
                status = "PASS" if has_policy and has_data else "WARN"
                if not use_palace and not has_policy:
                    status = "MISSING_POLICY"
                
                # 提取摘要
                summary = output.replace('\n', ' ')[:50]
                policy_brief = "YES" if has_policy else "NO"
                
                print(f"| {i+1} | {q[:15]} | {mode} | {summary} | {policy_brief} | {status} |")
            except Exception as e:
                print(f"| {i+1} | {q[:15]} | {mode} | ERROR | - | FAIL |")
                print(f"Details: {str(e)}")
            
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run_comparison())
