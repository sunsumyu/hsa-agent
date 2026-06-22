import os
import sys
from loguru import logger

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.tools import search_expert_knowledge

def test_retrieval():
    # 1. 精准术语检索 (验证 BM25)
    print("\n--- Testing Keyword Retrieval (BM25) ---")
    query_keyword = "fqz_all_yy_yd_1"
    res_keyword = search_expert_knowledge.invoke(query_keyword)
    print(f"Query: {query_keyword}\nResult:\n{res_keyword[:500]}...")

    # 2. 语义逻辑检索 (验证 Vector)
    print("\n--- Testing Semantic Retrieval (Vector) ---")
    query_semantic = "如何识别挂床住院行为"
    res_semantic = search_expert_knowledge.invoke(query_semantic)
    print(f"Query: {query_semantic}\nResult:\n{res_semantic[:500]}...")

if __name__ == "__main__":
    test_retrieval()
