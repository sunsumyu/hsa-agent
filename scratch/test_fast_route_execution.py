# -*- coding: utf-8 -*-
"""
HSA 快速直通路由优化效果验证脚本 (End-to-End Fast-Route Validation)
=================================================================
验证在命中已知审计规则时，系统能否在数秒内物理级直接输出高保真审计报告，
完全避开 Coder/Reporter 的 LLM 漫长推理。
"""
import os
import sys
import asyncio
import time
from loguru import logger
from langchain_core.messages import HumanMessage

sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# 强制 Windows 终端输出 UTF-8
if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from app.core.agent_graph import workflow
from app.core.observability import init_observability, shutdown_observability

async def main():
    # 1. 初始化本地脱机观测系统
    init_observability()
    
    prompt = "对全市结算数据进行性别冲突检查：找出男性患者产生妇科或产科费用的异常明细。"
    logger.info(f"发送测试请求: '{prompt}'")
    
    start_time = time.time()
    
    # 模拟输入 state
    initial_state = {
        "messages": [HumanMessage(content=prompt)],
        "tasks": [],
        "sql_query": "",
        "sql_history": [],
        "raw_data": "",
        "audit_findings": [],
        "structured_report": None,
        "metadata": {
            "user_question": prompt,
            "session_id": "test_fast_route_session"
        },
        "session_id": "test_fast_route_session",
        "error_log": "",
        "audit_feedback": None,
        "retry_count": 0,
        "human_input": None,
        "is_awaiting_human": False,
        "sql_validated": False,
        "loop_count": 0,
        "next_step": "",
        "schema_hint": None,
        "execution_trace": [],
        "methodology": "",
        "temp_table": None
    }
    
    logger.info("🚀 正在执行 Agent Graph 流程...")
    
    try:
        # 执行图
        result = await workflow.ainvoke(initial_state)
    except Exception as e:
        logger.exception(f"执行异常: {e}")
        return
        
    end_time = time.time()
    elapsed = end_time - start_time
    
    print("\n" + "="*80)
    print("           HSA 智能体「物理直通优化」实测执行统计 ")
    print("="*80)
    print(f"【端到端总耗时】: {elapsed:.4f} 秒  (物理极限提速！)")
    
    metadata = result.get("metadata") or {}
    fast_route_id = metadata.get("fast_route_id")
    print(f"【是否命中直通】: {fast_route_id is not None} (命中规则: {fast_route_id})")
    
    print(f"【执行 SQL 语句】:")
    print("-" * 80)
    print(result.get("sql_query", "N/A").strip())
    print("-" * 80)
    
    report = result.get("structured_report")
    if report:
        print("\n【生成的 5 章节审计报告 (首段展示)】:")
        print("." * 80)
        lines = report.markdown.split("\n")
        print("\n".join(lines[:25]) + "\n...")
        print("." * 80)
        print(f"\n【报告综合评估】:")
        print(f"  - 风险等级: {report.risk_level}风险")
        print(f"  - 涉案金额: ¥{report.total_amount:,.2f}")
        print(f"  - 违规条数: {report.finding_count} 条")
    else:
        print("\n❌ 未能生成结构化报告。")
    print("="*80)
    
    # 优雅停止观测
    shutdown_observability()

if __name__ == "__main__":
    asyncio.run(main())
