# -*- coding: utf-8 -*-
"""
HSA Diagnostic Runner for Specific Case
"""
import os, sys, asyncio, json, time, io
sys.path.append(os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["DISABLE_AUDIT_CACHE"] = "true"  # Disable caching to force fresh executions
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from app.core.agent_graph import workflow
from app.infra.model_manager import model_manager
from app.infra.usage_tracker import usage_tracker
from loguru import logger

# Set logger to DEBUG to capture detailed logs
logger.remove()
logger.add(sys.stdout, level="DEBUG")

TEST_CASES = {
    "QA-CUST-23": {
        "id": "QA-CUST-23", 
        "tag": "Therapist Time Overlap / Cloning", 
        "prompt": "查一下理疗科和康复科的执行大夫。你去按每一分钟去排一下他们做一对一手法治疗的单子，看看有没有哪个大夫练了分身术，在同一时间段里，系统上竟然显示他同时在给五六个病号做必须要医生亲自上手推拿的项目？这种纯粹就是护士拿着卡乱刷、甚至连病号都没来直接挂空床的虚假理疗。"
    },
    "QA-CUST-24": {
        "id": "QA-CUST-24", 
        "tag": "Service Without Mandatory Consumables", 
        "prompt": "去扫一遍血透和骨科大手术的单子，查那种干活不用工具的灵异事件。比如医院收了高昂的血液透析治疗费，但是你在他当天的耗材明细里，连个透析器或者透析管路都找不到；或者骨科收了脊柱内固定手术费，却没看见用任何钛钉钛板的。这就叫只收手工费不走耗材，要么是串换项目套现，要么就是彻头彻尾的虚构手术，把这种自相矛盾的单子全抓出来。"
    },
    "QA-CUST-25": {
        "id": "QA-CUST-25", 
        "tag": "Biological Limit / Impossible Dental History", 
        "prompt": "把口腔科的医保结算拉出来，尤其是拔牙和根管治疗的。写个逻辑去追溯每个病号的历史看牙记录。正常人一共也就二三十颗牙，你给我找找有没有哪个狠人，在过去两三年里跨了不同的牙科诊所，累计被拔了四五十颗牙的？或者更离谱的，他去年在一家诊所已经拔了左下的大牙，今年在另一家诊所又把同一颗牙给拔了一次的。这种骗医保不仅造假，连基本的生理常识都不要了。"
    },
    "QA-CUST-26": {
        "id": "QA-CUST-26", 
        "tag": "Automated Batch Billing / Time-Series Anomalies", 
        "prompt": "查查乡镇卫生院和村卫生室的门诊统筹刷单。你去把每天的结算流水按时间戳精细排个序，看有没有这种极端诡异的现象：连续十几个不同的病号，他们不仅开出来的药或者理疗项目一模一样，而且相互之间结算的时间精准地只隔了三五秒钟，就像是用机器脚本在批量扫码一样。这绝对是村医大半夜把全村的医保卡收集起来，放在刷卡机上集中流水线套现的团伙作案。"
    }
}

async def run_case(case_id):
    case = TEST_CASES.get(case_id)
    if not case:
        print(f"Case {case_id} not found.")
        return

    print("=" * 80)
    print(f"RUNNING DIAGNOSTIC FOR {case_id}: {case['tag']}")
    print(f"Prompt: {case['prompt']}")
    print("=" * 80)

    inputs = {
        "messages": [("user", case["prompt"])],
        "session_id": f"DIAG_{case_id}_{int(time.time())}"
    }

    t0 = time.time()
    try:
        state = await workflow.ainvoke(inputs, config={"recursion_limit": 30})
        elapsed = time.time() - t0
        print("\n" + "=" * 80)
        print(f"EXECUTION COMPLETE IN {elapsed:.2f}s")
        print("=" * 80)
        
        print("\n[State Keys]")
        for k in sorted(state.keys()):
            val = state[k]
            if k in ["messages", "raw_data", "structured_report"]:
                print(f"  - {k}: ({type(val)}) ... truncated")
            else:
                try:
                    # Safe print encoding
                    safe_val = str(val).encode('gbk', errors='replace').decode('gbk')
                    print(f"  - {k}: {safe_val}")
                except Exception:
                    print(f"  - {k}: [repr] {repr(val)}")

        print("\n[SQL Query (state.get('sql_query'))]")
        try:
            print(str(state.get("sql_query")).encode('gbk', errors='replace').decode('gbk'))
        except Exception:
            print(repr(state.get("sql_query")))

        print("\n[SQL History (state.get('sql_history'))]")
        try:
            print(str(state.get("sql_history")).encode('gbk', errors='replace').decode('gbk'))
        except Exception:
            print(repr(state.get("sql_history")))

        print("\n[Execution Trace]")
        for trace in state.get("execution_trace", []):
            try:
                print(f"  - {str(trace).encode('gbk', errors='replace').decode('gbk')}")
            except Exception:
                print(f"  - [repr] {repr(trace)}")

        print("\n[Last AIMessage Content]")
        msgs = state.get("messages", [])
        ai_msgs = [m for m in msgs if getattr(m, "type", "") == "aimessage" or hasattr(m, "content") and not isinstance(m, tuple) and getattr(m, "type", "") == "ai"]
        if ai_msgs:
            try:
                print(str(ai_msgs[-1].content).encode('gbk', errors='replace').decode('gbk'))
            except Exception:
                print(repr(ai_msgs[-1].content))
        else:
            print("No AI message found.")
            
        print("\n[Rendered Report Markdown]")
        rep = state.get("structured_report")
        if rep and hasattr(rep, "markdown"):
            try:
                print(str(rep.markdown).encode('gbk', errors='replace').decode('gbk'))
            except Exception:
                print(repr(rep.markdown))
        else:
            print("No rendered report markdown found.")
            
    except Exception as e:
        print(f"Error during workflow run: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    case_id = sys.argv[1] if len(sys.argv) > 1 else "QA-CUST-23"
    asyncio.run(run_case(case_id))
