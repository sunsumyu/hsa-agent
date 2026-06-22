# -*- coding: utf-8 -*-
import os, sys
sys.path.append(os.getcwd())

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from app.memory.message_sanitizer import trim_and_sanitize

# Mock history of messages
left = [
    SystemMessage(content="system 1"),
    SystemMessage(content="system 2 (GSSC payload)"),
    HumanMessage(content="human 1"),
    HumanMessage(content="human 2 (planner)"),
    AIMessage(content="", tool_calls=[{"name": "lookup_medical_schema", "args": {}, "id": "c1"}]),
    ToolMessage(content="tool 1 result", tool_call_id="c1"),
    AIMessage(content="", tool_calls=[{"name": "get_table_schema", "args": {}, "id": "c2"}]),
    ToolMessage(content="tool 2 result", tool_call_id="c2"),
    AIMessage(content="", tool_calls=[{"name": "execute_audit_sql", "args": {}, "id": "c3"}]),
    ToolMessage(content="tool 3 result", tool_call_id="c3"),
]

# Next loop returns:
right = [
    AIMessage(content="", tool_calls=[{"name": "execute_audit_sql", "args": {}, "id": "c4"}]),
    ToolMessage(content="tool 4 result", tool_call_id="c4"),
]

print("Left length:", len(left))
print("Right length:", len(right))

merged = trim_and_sanitize(left, right, max_total=40, keep_head=5, keep_tail=25)
print("Merged length with max_total=40:", len(merged))
for i, m in enumerate(merged):
    print(f"  {i}: {m.__class__.__name__}(type={m.type}, content={repr(m.content)}, tool_calls={getattr(m, 'tool_calls', None)})")

print("\nMerged length with max_total=10 (default in state.py):")
merged_10 = trim_and_sanitize(left, right, max_total=10, keep_head=2, keep_tail=6)
print("Merged length:", len(merged_10))
for i, m in enumerate(merged_10):
    print(f"  {i}: {m.__class__.__name__}(type={m.type}, content={repr(m.content)}, tool_calls={getattr(m, 'tool_calls', None)})")
