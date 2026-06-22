import json
from app.memory.message_sanitizer import compress_tool_content
from langchain_core.messages import ToolMessage

# Mock a large SQL result
large_data = [
    {"psn_no": f"P{i}", "setl_id": f"S{i}", "medfee_sumamt": 100.0, "violation_type": "Repeat Billing"}
    for i in range(100)
]
content = json.dumps(large_data)

msg = ToolMessage(content=content, tool_call_id="call_123")
print(f"Original length: {len(msg.content)}")

compressed_list = compress_tool_content([msg])
compressed = compressed_list[0]
print(f"Compressed length: {len(compressed.content)}")
print(f"Compressed content: {compressed.content}")
print(f"Additional kwargs: {compressed.additional_kwargs.keys()}")
if "_raw_content" in compressed.additional_kwargs:
    print(f"Raw content stored (first 50 chars): {compressed.additional_kwargs['_raw_content'][:50]}...")
