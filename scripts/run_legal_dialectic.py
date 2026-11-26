#!/usr/bin/env python
"""
scripts/run_legal_dialectic.py
==============================
法律多轮辩法智能体交互式终端 CLI
支持当事人/律师在终端输入案件描述、证据信息，开展红蓝对抗辩法推演与三段论心证生成。
"""

import asyncio
import sys
import os

# 将项目根目录加入模块搜索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState

def print_banner():
    banner = """
========================================================================
     ⚖️  Argus Legal Agent - 司法三段论与红蓝对抗多轮辩法终端  ⚖️
========================================================================
 特性说明:
 1. 物理真实对齐: 基于《民法典》与法定构成要件库 (StatuteRegistry)
 2. 神经符号硬门禁: 诉讼时效计算 / 4倍LPR利息截断 / 自相矛盾诉求拦截
 3. 红蓝攻防对抗: 原告进攻主张 vs 被告事实抗辩 vs 法官心证意见书
========================================================================
    """
    print(banner)

def _select_cause() -> str:
    """Prompt the user to choose a legal cause of action."""
    print("请选择案由:")
    print("  [1] 民间借贷纠纷 (默认)")
    print("  [2] 买卖合同纠纷")
    choice = input("请输入选项 (1/2, 直接回车默认为 1): ").strip()
    return "买卖合同纠纷" if choice == "2" else "民间借贷纠纷"


def _init_case_state(thread_id: str, cause: str) -> LegalCaseState:
    """Initialize blank LegalCaseState for an interactive dialectic session."""
    return {
        "thread_id": thread_id,
        "messages": [],
        "metadata": {"cause": cause, "user_question": ""},
        "current_step": "START",
        "error_log": None,
        "retry_count": 0,
        "is_awaiting_human": False,
        "case_facts": [],
        "evidence_items": [],
        "dispute_foci": [],
        "active_focus_id": None,
        "dialectic_history": [],
        "final_disposition": None,
    }


def _render_dialectic_result(state: LegalCaseState) -> None:
    """Render extracted facts, evidence, dispute foci, and gate status."""
    facts = state.get("case_facts", [])
    evidence = state.get("evidence_items", [])
    foci = state.get("dispute_foci", [])
    err = state.get("error_log")
    disposition = state.get("final_disposition")

    print("\n📋 【事实与证据池概览】")
    print(f"  * 认定理算事实: {len(facts)} 项")
    for f in facts[-2:]:
        print(f"    - {f.narrative}")
    print(f"  * 关联证据凭单: {len(evidence)} 份")
    for e in evidence[-2:]:
        print(f"    - [{e.evidence_type}] {e.title}")

    print("\n🎯 【争议焦点识别】")
    for idx, fc in enumerate(foci, 1):
        print(f"  {idx}. [{fc.focus_id}] {fc.issue_statement} (倾向: {fc.adjudication_tendency})")

    print("\n🛡️  【神经符号门禁校验 (System 2)】")
    if err:
        print(f"  🚨 [门禁拦截警告]: {err}")
    else:
        print("  ✅ [门禁全量通过]: 诉讼时效未逾期、无主张自相矛盾、必备交付要件证据链闭环。")

    if disposition:
        print("\n" + disposition)


async def main():
    """Run the interactive legal dialectic CLI loop."""
    print_banner()
    graph = build_legal_graph()
    cause = _select_cause()
    print(f"\n已选择案由: 【{cause}】")
    print("提示: 输入 'exit' 或 'quit' 退出辩法。\n")

    turn_counter = 1
    state = _init_case_state("cli-dialectic-session", cause)

    while True:
        try:
            print("-" * 72)
            user_input = input(f"第 {turn_counter} 轮 - 请输入案情事实、证据或对方抗辩理由:\n> ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n[系统] 已退出辩法终端。")
                break

            state["metadata"]["user_question"] = user_input
            print("\n⏳ 正在执行司法三段论推演与对抗模拟...")
            state.update(await graph.ainvoke(state))
            _render_dialectic_result(state)
            turn_counter += 1
        except KeyboardInterrupt:
            print("\n[系统] 用户中断，退出。")
            break
        except Exception as ex:
            print(f"\n❌ 执行异常: {ex}")

if __name__ == "__main__":
    asyncio.run(main())
