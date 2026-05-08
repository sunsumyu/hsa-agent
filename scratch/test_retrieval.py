from app.semantic_layer import SemanticRetriever
import os

def test_retrieval():
    sr = SemanticRetriever()
    sr.build_index()
    q = "请分析患者 PSN_20210001 在 2021 年 7 月至 10 月间的就医行为是否存在异常？"
    results = sr.get_relevant_columns([q])
    print(f"Query: {q}")
    for r in results:
        print(f"Table: {r['table']}, Column: {r['column']}, Desc: {r['desc']}")

if __name__ == "__main__":
    test_retrieval()
