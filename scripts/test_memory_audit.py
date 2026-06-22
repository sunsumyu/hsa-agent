import os
import sys
from loguru import logger

# 确保能加载 app 模块
sys.path.append(os.getcwd())

from app.memory.semantic_memory import cognitive_memory_manager
from app.core.agent_graph import get_graph_executor

def test_memory_loop():
    executor, _ = get_graph_executor()
    logger.info("=== [Phase 1: 经验灌输] ===")
    # 手动模拟一次成功的审计发现并存入长期记忆
    experience_topic = "重复收费审计"
    experience_content = (
        "审计经验：针对重复收费（如同一天多次结算），应使用以下 SQL 逻辑：\n"
        "SELECT psn_no, setl_time, count(*) as cnt FROM fqz_gz_jzsj_all_ql "
        "GROUP BY psn_no, setl_time HAVING cnt > 1. \n"
        "核心证据：PSN_NO 是患者唯一标识，SETL_TIME 是结算日期。"
    )
    cognitive_memory_manager.add_audit_event(experience_content, importance=1.0, topic=experience_topic)
    
    logger.info("=== [Phase 2: 触发带有记忆的稽核] ===")
    user_input = "帮我查查 2024 年是否有重复收费的违规行为，给出证据。"
    
    # 运行 Agent Graph
    config = {"configurable": {"thread_id": "memory_test_001"}}
    inputs = {"messages": [("user", user_input)]}
    
    logger.info(f">>> 用户指令: {user_input}")
    
    for output in executor.stream(inputs, config=config):
        for node_name, state in output.items():
            logger.info(f"--- 节点执行完毕: {node_name} ---")
            if "messages" in state:
                last_msg = state["messages"][-1]
                # 我们重点观察 Planner 节点是否输出了“召回经验”
                if node_name == "planner":
                    content = last_msg.content
                    if "审计经验召回" in content or "历史相关" in content:
                        logger.success("✅ 验证成功：Planner 已成功从本地语义记忆中召回了历史经验！")
                    else:
                        logger.warning("⚠️ Planner 未能显式展示召回内容，请检查 prompts.py 是否包含记忆槽位。")
                
                # 打印最后一条消息的简要内容
                # logger.info(f"输出内容预览: {str(last_msg.content)[:100]}...")

if __name__ == "__main__":
    test_memory_loop()
