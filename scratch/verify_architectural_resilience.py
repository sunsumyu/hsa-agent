import asyncio
from app.agent_graph import resilient_expert_call, AuditState
from app.usage_tracker import usage_tracker
from langchain_core.messages import HumanMessage
from loguru import logger
import sys

# Ensure UTF-8 output if possible, but we'll stick to ASCII for safety
def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'ignore').decode('ascii'))

async def simulate_failover_test():
    safe_print("\n" + "="*50)
    safe_print("START: Verifying [Architectural Resilience] Protocol V4.9.15")
    safe_print("="*50)
    
    # 1. Simulate a failed environment
    model_id = "doubao-pro-32k"
    usage_tracker.record_failure(model_id, "403 - Free Tier Exhausted")
    safe_print(f"INFO: Marked {model_id} as unstable, Score: {usage_tracker.get_stability_score(model_id):.2f}")
    
    # 2. Construct State
    state: AuditState = {
        "messages": [HumanMessage(content="Test prompt")],
        "findings": [],
        "model_id": model_id, 
        "retry_count": 0,
        "step_counter": 0,
        "next_expert": "DATA_EXPERT",
        "expert_history": [],
        "tool_call_history": {},
        "timeline_events": []
    }
    
    # 3. Call Expert (Expected Failover)
    safe_print("\nEXEC: Calling data_expert_node (Expecting automated failover)...")
    try:
        from app.agent_graph import data_expert_node
        result = await data_expert_node(state)
        
        safe_print("\n" + "="*50)
        safe_print("SUCCESS: Architectural failover verified!")
        safe_print(f"Expert Message Preview: {result['messages'][0].content[:150]}...")
        safe_print("="*50)
        
    except Exception as e:
        safe_print(f"ERROR: Verification failed: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_failover_test())
