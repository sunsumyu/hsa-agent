import os
import pytest
from dotenv import load_dotenv
load_dotenv()

from langchain_core.documents import Document
from app.core.memory.qdrant_vector_adapter import qdrant_vector_adapter, path_to_collection_name

class MockDeterministicEmbeddings:
    """提供非全零的测试嵌入，以在 CI / 离线模式下正确计算余弦相似度"""
    def embed_documents(self, texts):
        res = []
        for i, t in enumerate(texts):
            vec = [0.01] * 384
            vec[i % 384] = 1.0
            res.append(vec)
        return res

    def embed_query(self, text):
        vec = [0.01] * 384
        vec[0] = 1.0  # 与第一个文档高度重合
        return vec

@pytest.mark.skipif(
    not os.getenv("QDRANT_URL") or not os.getenv("QDRANT_API_KEY"),
    reason="Qdrant Cloud 凭据未配置，跳过在线集成测试"
)
def test_qdrant_cloud_live_roundtrip():
    test_storage = "tests/live_audit_test"
    col_name = path_to_collection_name(test_storage)

    client = qdrant_vector_adapter._get_client()
    assert client is not None, "Qdrant 客户端未连接"

    # 清理遗留
    try:
        client.delete_collection(col_name)
    except Exception:
        pass

    embeddings = MockDeterministicEmbeddings()

    try:
        docs = [
            Document(
                page_content="医保避坑指南: 男性使用妇科诊疗项目必须在 WHERE 子句中正向约束 gend LIKE '1%'",
                metadata={"archetype": "exclusion", "rule": "R_MALE_GYN"}
            ),
            Document(
                page_content="医保结算审核: 门诊慢特病药品跨机构高频超量购药需在参保人维度做 GROUP BY 统计",
                metadata={"archetype": "drug_resale", "rule": "R_DRUG_FREQ"}
            ),
        ]

        # 1. 写入真实 Qdrant Cloud
        ok = qdrant_vector_adapter.add_documents(test_storage, embeddings, docs)
        assert ok is True

        # 2. 真实云端检索
        results = qdrant_vector_adapter.search_with_score(
            test_storage,
            embeddings,
            query="男性做妇科检查违规怎么查",
            k=2
        )
        assert len(results) >= 1
        top_doc, score = results[0]
        assert "男性使用妇科诊疗项目" in top_doc.page_content
        assert top_doc.metadata.get("archetype") == "exclusion"
        assert score > 0.5

    finally:
        # 3. 清理云端测试集合
        try:
            client.delete_collection(col_name)
        except Exception:
            pass
