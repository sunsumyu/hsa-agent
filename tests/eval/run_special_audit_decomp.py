import asyncio
import os
import sys
from loguru import logger
from dotenv import load_dotenv

# 确保能导入 app 包
sys.path.append(os.getcwd())

from app.core.agent_graph import AgentGraph
from app.infra.usage_tracker import usage_tracker

load_dotenv()
import app.core.agent_graph
print(f"\n[DEBUG_PATH] Loading agent_graph from: {app.agent_graph.__file__}")

# [V37.7] 专项审计：高频购药异常（生产口径校准版，数据已确认存在）
SPECIAL_AUDIT_TASK = {
    "id": "SPECIAL_HIGH_FREQ_DRUG_2024",
    "name": "2024 年度零售药店高频购药专项审计",
    "prompt": """
    【专项审计核心任务：零售药店高频购药异常侦测】
    1. 立即调用 audit_medical_rule 工具，规则ID为 'HIGH_FREQ_DRUG_PURCHASE'。
    2. 该规则将扫描 2024 年全量零售药店结算数据，识别同一参保人在同一药店购药次数异常偏高（>=10次）的记录。
    3. 获取购药频次最高的前 5 名参保人信息（psn_no、药店名、购药次数、总金额、基金支付额）。
    4. 对购药频次最高的参保人，调用 execute_audit_sql 进一步查询其具体购药记录，分析购药间隔是否过于密集（如1天内多次购药）。
    5. 生成一份包含证据链和违规金额的专项审计简报。
    """
}

async def run_special_audit():
    logger.info(f"🚀 启动专项大规模审计: {SPECIAL_AUDIT_TASK['name']}")
    
    # 初始化状态
    initial_state = {
        "messages": [("user", SPECIAL_AUDIT_TASK["prompt"])],
        "tasks": [],
        "retry_count": 0,
        "is_awaiting_human": False,
        "sql_validated": False,
        "case_id": SPECIAL_AUDIT_TASK["id"]
    }
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        # 运行 Agent Workflow
        app = AgentGraph().compile()
        final_state = await app.ainvoke(initial_state)
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        print("\n" + "="*60)
        print("V37.5 Special Audit Report Summary")
        print("="*60)
        print(f"Task: {SPECIAL_AUDIT_TASK['name']}")
        print(f"Status: COMPLETED")
        print(f"Time Elapsed: {elapsed:.1f}s")
        print("="*60)
        
        # 打印审计结论摘要
        if "messages" in final_state:
            msgs = final_state["messages"]
            print(f"\n[DEBUG] 消息总数: {len(msgs)}")
            for i, m in enumerate(msgs):
                # 兼容元组格式 [("user", "...")] 和消息对象
                if isinstance(m, tuple):
                    role = m[0].upper()
                    content = m[1]
                else:
                    role = "USER" if "Human" in str(type(m)) else ("AI" if "AI" in str(type(m)) else "TOOL" if "Tool" in str(type(m)) else "SYSTEM")
                    content = getattr(m, 'content', str(m))
                # [V37.6] 编码防御：清洗非 ASCII 字符以防控制台崩溃
                clean_content = "".join([c if ord(c) < 128 or '\u4e00' <= c <= '\u9fff' else '?' for c in str(content)])
                print(f"  - Msg {i} ({role}): {clean_content[:60]}...")

            last_msg = msgs[-1][1] if isinstance(msgs[-1], tuple) else getattr(msgs[-1], 'content', str(msgs[-1]))
            print("\n>>> [审计结论预览]:\n")
            print(last_msg[:1000] + "..." if len(last_msg) > 1000 else last_msg)
            
            # 检查是否有原始数据
            raw_data = final_state.get("raw_data", "")
            if raw_data:
                print(f"\n[DEBUG] 抓取到原始数据片段: {str(raw_data)[:200]}...")
            else:
                print("\n[DEBUG] 警告：未检测到 raw_data 状态。")
            
            # [V37.5] 持久化报告 (强制 UTF-8)
            report_path = "data/special_audit_decomp_2024.md"
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(last_msg)
                print(f"\n[OK] 完整报告已存入: {report_path}")
            except Exception as fe:
                print(f"\n[ERR] 报告保存失败: {fe}")
            
    except Exception as e:
        logger.error(f"专项审计执行崩溃: {e}")
    
    # 强制输出 Token 账单
    print(usage_tracker.get_usage_report())

if __name__ == "__main__":
    asyncio.run(run_special_audit())
