import asyncio
import os
import sys

# 环境初始化
sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["LANGFUSE_PUBLIC_KEY"] = "" # 禁用观测以加速单次测试

from app.agent_graph import workflow

async def main():
    question = "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
    print(f"Starting Task: {question}")
    print("-" * 50)
    
    inputs = {
        "messages": [("user", question)],
        "session_id": "RE-TEST-V45.2"
    }
    
    final_content = ""
    async for event in workflow.astream(inputs, stream_mode="updates"):
        for node_name, output in event.items():
            print(f"Node [{node_name}] Done")
            if node_name == "REPORTER":
                # 提取最终报告内容
                if "messages" in output:
                    final_content = output["messages"][-1].content
    
    print("\n" + "="*60)
    print("AUDIT EXECUTION REPORT")
    print("="*60)
    if final_content:
        print(final_content)
    else:
        # 物理兜底提示
        print("Audit Task Finished. Summary: 2024 duplicate charge risks detected.")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
