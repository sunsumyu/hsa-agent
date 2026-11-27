"""
tests/unit/memory/test_experience_deep_red.py
============================================
[Matt Pocock Deep Module Red Test] 经验记忆沉淀与向量索引解耦架构审计
"""

import os
import json
import warnings
from unittest.mock import MagicMock
import pytest
from langchain_core.documents import Document

from app.core.memory.experience import ExperienceManager, POOL_FILE, INDEX_PATH


def test_experience_module_import_clean_without_deprecation_warning():
    """验证模块导入时未触发 langchain-community 弃用告警，且无全局 FAISS 顶层导入污染"""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        import importlib
        import app.core.memory.experience
        importlib.reload(app.core.memory.experience)
        
        community_warnings = [
            w for w in recorded
            if issubclass(w.category, DeprecationWarning) and "langchain-community" in str(w.message)
        ]
        assert len(community_warnings) == 0, f"发现未抑制的弃用告警: {[str(w.message) for w in community_warnings]}"


def test_experience_manager_save_and_retrieve_flow(tmp_path, monkeypatch):
    """验证经验保存与语义检索格式化输出"""
    test_pool = str(tmp_path / "test_pool.json")
    test_index = str(tmp_path / "faiss_index")
    monkeypatch.setattr("app.core.memory.experience.POOL_FILE", test_pool)
    monkeypatch.setattr("app.core.memory.experience.INDEX_PATH", test_index)

    mgr = ExperienceManager()
    
    # 模拟向量适配器
    fake_adapter = MagicMock()
    fake_doc = Document(
        page_content="排查重复住院费用",
        metadata={
            "intent": "排查重复住院费用",
            "golden_sql": "SELECT psn_no FROM fqz_gz_jzsj_all_ql GROUP BY psn_no HAVING count(*) > 1",
            "ts": 123456
        }
    )
    fake_adapter.search.return_value = [fake_doc]
    monkeypatch.setattr(mgr, "_adapter", fake_adapter)
    monkeypatch.setattr("app.core.memory.experience.get_embeddings", lambda: MagicMock())

    # 1. 保存正常有效经验
    mgr.save_audit_experience(
        tasks=["排查重复住院费用"],
        sql="SELECT psn_no FROM fqz_gz_jzsj_all_ql GROUP BY psn_no HAVING count(*) > 1"
    )

    # 验证本地 pool.json 已写入
    with open(test_pool, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["intent"] == "排查重复住院费用"

    # 2. 检索历史案例
    result = mgr.get_relevant_experience(["排查重复住院费用"], k=1)
    assert "### 参考历史成功案例 (Semantic Match):" in result
    assert "意图: 排查重复住院费用" in result
    assert "```sql" in result
    assert "SELECT psn_no FROM fqz_gz_jzsj_all_ql" in result


def test_experience_manager_pool_rebuild_index_on_demand(tmp_path, monkeypatch):
    """验证当索引丢失但 pool.json 存在时，经验管理器能自动按需触发重建"""
    test_pool = str(tmp_path / "test_pool.json")
    test_index = str(tmp_path / "faiss_index")
    monkeypatch.setattr("app.core.memory.experience.POOL_FILE", test_pool)
    monkeypatch.setattr("app.core.memory.experience.INDEX_PATH", test_index)

    # 事先写入 pool.json
    pool_data = [
        {"intent": "意图1", "golden_sql": "SELECT 1", "ts": 1},
        {"intent": "意图2", "golden_sql": "SELECT 2", "ts": 2},
    ]
    with open(test_pool, "w", encoding="utf-8") as f:
        json.dump(pool_data, f, ensure_ascii=False)

    mgr = ExperienceManager()
    fake_adapter = MagicMock()
    fake_adapter.has_index.return_value = False
    fake_adapter.search.return_value = []
    fake_adapter.add_documents.return_value = True
    monkeypatch.setattr(mgr, "_adapter", fake_adapter)
    monkeypatch.setattr("app.core.memory.experience.get_embeddings", lambda: MagicMock())

    # 触发检索或初始化，当没有现成索引时应从 pool 重建
    mgr.get_relevant_experience(["意图1"])
    assert fake_adapter.add_documents.called
