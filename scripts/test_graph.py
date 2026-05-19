import os
import sys
import asyncio

# 确保项目根目录在 PYTHONPATH 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.agent_graph import audit_app
from langchain_core.messages import HumanMessage

async def main():
    # 强制标准输出使用 UTF-8，防止 Windows 环境中打印表情包崩溃
    import sys
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("Starting multi-agent graph logic test...")
    inputs = {
        "messages": [HumanMessage(content="分析广州市第一人民医院在2026年4月的结算数据，找出费用最高的前2笔记录。随后根据专家知识库检查是否存在违规风险（关注高额医疗费用及自费占比），并使用计算器复核自费比例，最后输出标准的稽核建议卡片。")],
        "model_id": "qwen-max"
    }
    
    # 运行图并流式输出节点变化
    async for event in audit_app.astream_events(inputs, version="v1"):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                print(content, end="|", flush=True)
        elif kind == "on_tool_start":
            print(f"\n[工具启动] {event['name']}: {event['data'].get('input')}")
        elif kind == "on_tool_end":
            print(f"\n[工具结束] {event['name']}")
        elif kind == "on_chain_start":
            if event["name"] == "LangGraph":
                print("\n[图启动]")
        elif kind == "on_chain_end":
            if event["name"] == "LangGraph":
                print("\n[图结束]")

if __name__ == "__main__":
    asyncio.run(main())
