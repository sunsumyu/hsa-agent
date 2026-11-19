# -*- coding: utf-8 -*-
"""
scripts/run_5_turns_7metrics_audit.py
======================================
基于 scratch/run_7metrics_bench.py (HSA 7-Dimension Benchmark) 核心案例库设计的
5 轮实战医保穿透式审计对话与判定测试。

针对 7 大评估维度 (Success, Recall, Precision, Faithfulness, Relevance, Professionalism, Interpretability)
彻底解决前次纯文本提问导致模型脑补 "XX例"、"XX元" 占位符的 Mock 感问题：
1. 每一轮递进式注入真实的业务字段、临床逻辑与 SQL 聚合产出的确切数据
2. 最后一轮底稿归集强制要求基于确切数据（例数、金额、明细）出具法律级别认定结论
3. 挂载 LangSmith 链路聚合 (Thread) 与 7-Dimension 裁判打标数据飞轮
"""

import asyncio
import sys
import os
import uuid
import time
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from langchain_core.messages import HumanMessage, SystemMessage
from app.core.container import ServiceProvider
from app.core.bootstrap import register_services
from app.core.observability import SessionContextManager, PIISanitizer
from app.infra.model_manager import model_manager

# 5 轮全真案例交互设计 (精选自 run_7metrics_bench.py 经典案例库)
FIVE_TURNS_7METRICS_SCRIPT = [
    (
        "Round 1: 目录层级包含与拆分重复收费 (QA-CUST-14)",
        "排查发现某三甲医院骨科在收取'经皮椎体后凸成形术'打包费后，又对项目内涵中包含的'球囊充盈扩张加压装置'单独计费。请依据国家医保服务项目内涵规范，阐述该行为属于何种违规形式？在明细表 fqz_fymx_test 中应通过哪些字段比对来锁定此类重复计费？控制在 2 句话以内。"
    ),
    (
        "Round 2: DRG 旋转门分解住院时间窗排查 (QA-CUST-16)",
        "顺藤摸瓜发现该院骨科存在'术后第5天出院，次日（间隔<24小时）转入同院康复科以截瘫/神经损伤康复再次入院'的模式。院方抗辩称两个科室核算独立且主诊断不同。作为国家检查组，请给出反驳院方抗辩的核心政策依据，并指明在 ClickHouse 中跨就诊计算时间差应使用哪个窗口函数？控制在 2 句话以内。"
    ),
    (
        "Round 3: 虚构诊疗与无耗材硬伤排查 (QA-CUST-24)",
        "扩大排查范围至血透与骨科手术：若医院大额计费了'血液透析'或'脊柱内固定术'，但关联的耗材明细中根本没有'透析器/管路'或'钛钉钛板'（干活无工具）。这触犯了什么临床反模式？在数据库审计中如何构建治疗项目与高值耗材的伴生互斥校验？控制在 2 句话以内。"
    ),
    (
        "Round 4: 医生微观时序重叠与分身术排查 (QA-CUST-23)",
        "针对康复科的物理治疗（PT/OT手法），查实李某某医生在 2024-05-18 上午 09:00-10:00 期间，同时在系统上产生了 6 名不同患者的'一对一徒手推拿'费用（每人次标准时长45分钟）。这种微观时序冲突说明了什么问题？在事实认定中应如何定性？控制在 2 句话以内。"
    ),
    (
        "Round 5: 真实穿透数据注入与底稿法定事实认定 (彻底消除XX占位符)",
        "【真实审计取证数据汇总注入】\n"
        "- 机构：江城市第二人民医院（骨科、康复科）\n"
        "- 核查周期：2023年1月 - 2024年6月\n"
        "- 事实1 (球囊重复收费)：SQL 查实 47 人次，单次重复计费 3,800 元，违规金额累计 178,600.00 元\n"
        "- 事实2 (跨科分解住院)：SQL 查实 19 人次出院次日跨科转入康复科，涉嫌套取次均定额基金 243,200.00 元\n"
        "- 事实3 (康复医生分身术)：涉及虚假记录 128 人次，违规金额 51,200.00 元\n"
        "三项合计违规总金额：473,000.00 元。\n"
        "【任务要求】：\n"
        "请严格依据上述【真实审计取证数据】（必须精确引用 47人次、19人次、128人次与 473,000.00元真实数字，严禁出现'XX例'或'XX元'占位符），依照《医疗保障基金使用监督管理条例》第十五条、第三十八条，起草一份具有法律效力的现场审计事实认定底稿结论。"
    )
]

async def run_5_turns_audit():
    print("=" * 80, flush=True)
    print("启动基于 7-Dimension Benchmark 的 5 轮全真实战医保穿透审计对话评测", flush=True)
    print("=" * 80, flush=True)

    register_services()
    obs = ServiceProvider.resolve("observability")
    llm, mid = model_manager.get_adaptive_llm(model_id="ppio-lightweight")
    
    session_id = f"audit-7metrics-5turns-{uuid.uuid4().hex[:6]}"
    print(f"会话 ID (LangSmith Thread ID): {session_id}", flush=True)
    print(f"模型引擎通道: {mid}", flush=True)

    system_prompt = (
        "你是国家医疗保障局现场稽核飞行检查组核心专家 Agent，精通医保监管政策、ClickHouse 大数据穿透审计与医疗欺诈反模式。"
        "作答原则：\n"
        "1. 专业严谨、直击核心、法理兼备，结合临床诊疗常规与《医疗保障基金使用监督管理条例》。\n"
        "2. 当收到具体审计取证数据时，必须 100% 忠实引用真实数据与金额，坚决杜绝任何'XX'等虚构或占位符表达。"
    )
    history = [SystemMessage(content=system_prompt)]

    start_all = time.time()
    turn_results = []

    for turn_idx, (action_title, user_question) in enumerate(FIVE_TURNS_7METRICS_SCRIPT, 1):
        print(f"\n" + "-" * 75, flush=True)
        print(f"[Turn {turn_idx}/5] {action_title}", flush=True)

        governed_history = SessionContextManager.compact_history_if_needed(history, max_retained_turns=4)
        governed_history.append(HumanMessage(content=user_question))

        turn_config = SessionContextManager.build_turn_config(
            session_id=session_id,
            turn_index=turn_idx,
            action_name=action_title.split(":")[0],
            extra_meta={
                "benchmark_source": "scratch/run_7metrics_bench.py",
                "auditor_role": "state_hsa_inspector",
                "model_engine": mid
            }
        )
        final_config = obs.configure_run(
            node_name=f"7Metrics_Turn_{turn_idx}",
            session_id=session_id,
            base_config=turn_config
        )

        t0 = time.time()
        res = await llm.ainvoke(governed_history, config=final_config)
        t_elapsed = time.time() - t0

        history.append(HumanMessage(content=user_question))
        history.append(res)

        content_clean = str(res.content).strip()
        turn_results.append({
            "turn": turn_idx,
            "title": action_title,
            "response": content_clean,
            "elapsed": t_elapsed
        })
        print(f"   [AI 回复 ({t_elapsed:.2f}s)]:\n{content_clean}\n", flush=True)

    total_time = time.time() - start_all
    print("=" * 80, flush=True)
    print(f"5 轮全真穿透审计测试运行完毕！总耗时: {total_time:.2f}s", flush=True)
    print(f"LangSmith 聚合会话 Thread ID: {session_id}", flush=True)
    print("=" * 80, flush=True)

    # 保存测试结果为 JSON
    out_file = os.path.join(project_root, "scratch", "last_5turns_result.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "session_id": session_id,
            "total_time": total_time,
            "turns": turn_results
        }, f, ensure_ascii=False, indent=2)
    print(f"结果已持久化保存至: {out_file}", flush=True)

if __name__ == "__main__":
    asyncio.run(run_5_turns_audit())
