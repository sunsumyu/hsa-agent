import asyncio
import os
import sys
from loguru import logger
from langchain_core.messages import HumanMessage

# 修正 Python 路径
sys.path.append(os.getcwd())

from app.core.agent_graph import workflow as graph
from app.core.context import tenant_context

async def run_e2e_audit():
    logger.info("🛠️ 开始 HSA-Agent 工业级全链路 E2E 测试...")

    # 场景：徐汇区医保局核查“跨院重复住院”违规行为
    tenant_id = "DIST_310104"
    user_question = "核查是否存在跨院重复住院的异常情况，重点分析住院时间重叠的患者。"
    
    # 1. 设置租户上下文 (用于物理隔离注入)
    tenant_context.set(tenant_id)
    
    input_state = {
        "messages": [HumanMessage(content=user_question)],
        "metadata": {"user_question": user_question, "tenant_id": tenant_id},
        "retry_count": 0
    }

    # --- 第一轮：Cold Run (消耗 Token) ---
    logger.info("🚀 [Round 1] 开始首轮审计推演 (Cold Run)...")
    try:
        # 使用真实 LLM 运行
        result_1 = await graph.ainvoke(input_state)
        
        report_1 = result_1.get("report", "报告生成失败")
        logger.success("✅ 第一轮审计完成！")
        
        # 验证行政主体注入
        if "徐汇区医疗保障局" in report_1:
            logger.success("🛡️ [Isolation Check] 报告行政主体识别正确：徐汇区医疗保障局")
        else:
            logger.warning("⚠️ 报告行政主体识别异常")
            
        print(f"\n--- 第一轮报告摘要 ---\n{report_1[:400]}\n...")

        # --- 第二轮：Hot Run (验证动作压缩，节省 Token) ---
        logger.info("\n🚀 [Round 2] 模拟相同任务再次输入 (Hot Run)...")
        # 再次运行相同输入
        result_2 = await graph.ainvoke(input_state)
        
        if result_2.get("cache_hit"):
            logger.success("⚡ [CACHING] 成功命中动作压缩缓存！本次回复消耗 0 Token。")
            print(f"\n--- 第二轮报告 (来自缓存) ---\n{result_2.get('report', '')[:200]}...")
        else:
            logger.warning("⚠️ 未能命中动作缓存，请确认 Consolidator 逻辑是否正常触达。")

    except Exception as e:
        logger.error(f"❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_e2e_audit())
