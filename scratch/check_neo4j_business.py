import asyncio
import os
from dotenv import load_dotenv
from app.tools import query_fraud_ring

async def main():
    load_dotenv()
    print("--- [Graph Diagnostic] Testing Business Query ---")
    # 尝试查找患者和联系人的关系
    res = await query_fraud_ring("MATCH (p:Patient)-[r:HAS_CONTACT]->(c:Contact) RETURN p, r, c LIMIT 5")
    if res.get("status") == "ERROR":
        print(f"Error: {res.get('error_message')}")
    else:
        print(f"Result: Found {res.get('evidence_count')} nodes/relationships.")
        for rec in res.get("raw_evidence", []):
             print(rec)

if __name__ == "__main__":
    asyncio.run(main())
