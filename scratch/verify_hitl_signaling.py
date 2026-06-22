# [V61.0] HITL Signaling Verification Script
import asyncio
from unittest.mock import MagicMock, AsyncMock

# 模拟 AuditState 和 snapshot 对象
class MockSnapshot:
    def __init__(self, next_nodes, values):
        self.next = next_nodes
        self.values = values

# 模拟执行器
class MockExecutor:
    def __init__(self, snapshot):
        self.snapshot = snapshot
    
    async def aget_state(self, config):
        return self.snapshot

async def test_signal_logic(error_log_content, ai_content_exists):
    print(f"Testing with error_log='{error_log_content}', ai_content_exists={ai_content_exists}")
    
    # 建立测试场景
    snapshot = MockSnapshot(
        next_nodes=("EXECUTION:HUMAN_REVIEW",), 
        values={"error_log": error_log_content}
    )
    executor = MockExecutor(snapshot)
    config = {"configurable": {"thread_id": "test_session"}}
    ai_response_content = "Some content" if ai_content_exists else ""
    session_id = "test_session"
    
    # 模拟 main.py 中的探测逻辑
    output_chunks = []
    
    # --- 待验证逻辑开始 ---
    snapshot_res = await executor.aget_state(config)
    if snapshot_res.next:
        # print(f">>> [状态预警] 会话 {session_id} 处于挂起状态: {snapshot_res.next}")
        
        help_msg = ""
        if snapshot_res.values and snapshot_res.values.get("error_log"):
            error_log = str(snapshot_res.values["error_log"])
            if error_log.startswith("MODEL_REQUEST_HELP:"):
                help_msg = error_log.replace("MODEL_REQUEST_HELP:", "").strip()
        
        if not ai_response_content:
            output_chunks.append(f"[[[STATUS: 审计链路已挂起，正在等待人工业务指导...]]]\n\n")
            if help_msg:
                output_chunks.append(f"### 🚩 专家业务校准请求\n\nAgent 在执行审计取证时遇到关键疑虑：\n\n> {help_msg}\n\n---\n**💡 下一步指引**：\n请根据上述疑虑，直接在对话框中输入您的决策建议（如：“请按XX口径继续查询”或“忽略此项”），系统将自动恢复审计链路。")
            else:
                output_chunks.append("\n\n> [!IMPORTANT]\n> **审计链路中断**: 模型由于逻辑过于复杂请求人工接管。请在下方输入您的业务指导意见.")
    # --- 待验证逻辑结束 ---

    print("Resulting Output Chunks:")
    for i, chunk in enumerate(output_chunks):
        print(f"[{i}] {repr(chunk)}")
    print("-" * 20)

if __name__ == "__main__":
    asyncio.run(test_signal_logic("MODEL_REQUEST_HELP: 无法确定本月指哪个月", False))
    asyncio.run(test_signal_logic("DATABASE_ERROR: connection refused", False)) # 非求助中断
    asyncio.run(test_signal_logic("MODEL_REQUEST_HELP: 求助", True)) # 已有部分输出
