# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import json
from loguru import logger

sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from app.core.registry import skill_registry
from app.agents.coder_agent import coder_agent

async def debug_tool():
    all_tools = skill_registry.get_all_skills()
    
    metadata = {
        "fast_route_id": "GENDER_CONFLICT",
        "extra_filters": {}
    }
    state = {
        "metadata": metadata,
        "retry_count": 0,
        "messages": [],
        "execution_trace": []
    }
    
    tool_calls = [{
        "name": "audit_medical_rule",
        "args": {
            "rule_id": "GENDER_CONFLICT",
            "extra_filters": {}
        },
        "id": "call_fast_route_GENDER_CONFLICT"
    }]
    
    print("Calling invoke_tools_parallel in AuditCoderAgent:")
    results = await coder_agent._invoke_tools_parallel(tool_calls, all_tools, state)
    print(f"Raw parallel results length: {len(results)}")
    
    tc, res = results[0]
    print(f"Returned res type: {type(res)}")
    print(f"Is it string? {isinstance(res, str)}")
    if isinstance(res, str):
        print(f"Starts with {{? {res.strip().startswith('{')}")
        print(f"Snippet: {res[:200]}")
    
    print("Calling process_tool_results in AuditCoderAgent:")
    processed = coder_agent._process_tool_results(results, state)
    print(f"Processed output keys: {list(processed.keys())}")
    print(f"processed['sql_query']: {repr(processed.get('sql_query'))}")
    print(f"processed['sql_history']: {repr(processed.get('sql_history'))}")
    print(f"processed['raw_data'] snippet: {repr(processed.get('raw_data')[:100])}")

if __name__ == "__main__":
    asyncio.run(debug_tool())
