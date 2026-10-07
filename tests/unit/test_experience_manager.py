import pytest
from app.memory.experience import ExperienceManager

def test_experience_manager_anti_poisoning_rejects_contradiction(monkeypatch, tmp_path):
    """验证经验库防投毒门禁：包含恒假逻辑矛盾的 SQL 必须被拒绝入库，防止错误自强化重放"""
    # 隔离测试 pool 文件路径
    test_pool_file = str(tmp_path / "test_pool.json")
    monkeypatch.setattr("app.memory.experience.POOL_FILE", test_pool_file)
    
    mgr = ExperienceManager()
    monkeypatch.setattr(mgr, "_get_vector_store", lambda: None)
    
    # 模拟一个尝试存入的包含恒假矛盾的脏 SQL (二元全排除)
    bad_sql_1 = "SELECT setl_id FROM fqz_fymx_test WHERE gend NOT LIKE '1%' AND gend NOT LIKE '2%'"
    mgr.save_audit_experience(["排查男性使用宫内节育器"], bad_sql_1)
    
    # 验证没有被存入 pool
    pool = mgr._load_pool()
    assert len(pool) == 0, "包含二元全排除矛盾的 SQL 绝不能被固化为黄金经验！"

    # 模拟数值区间倒置矛盾的 SQL
    bad_sql_2 = "SELECT setl_id FROM fqz_fymx_test WHERE det_item_fee_sumamt > 1000 AND det_item_fee_sumamt < 100"
    mgr.save_audit_experience(["排查单笔大额费用"], bad_sql_2)
    pool = mgr._load_pool()
    assert len(pool) == 0, "包含数值区间倒置矛盾的 SQL 绝不能被固化为黄金经验！"

def test_experience_manager_accepts_valid_golden_sql(monkeypatch, tmp_path):
    """验证合规有效的 SQL 可以正常沉淀为语义经验"""
    test_pool_file = str(tmp_path / "test_pool.json")
    monkeypatch.setattr("app.memory.experience.POOL_FILE", test_pool_file)
    
    mgr = ExperienceManager()
    valid_sql = "SELECT psn_no, sum(det_item_fee_sumamt) FROM fqz_fymx_test WHERE gend LIKE '1%' GROUP BY psn_no"
    
    # Mock vector store saving to avoid downloading embeddings model during quick test
    monkeypatch.setattr(mgr, "_get_vector_store", lambda: None)
    
    mgr.save_audit_experience(["合规男性费用统计"], valid_sql)
    pool = mgr._load_pool()
    assert len(pool) == 1
    assert pool[0]["golden_sql"] == valid_sql
