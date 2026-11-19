"""
[Martin Fowler TDD - 红灯测试 (Red Test)]
测试目标：验证即将抽取的独立深模块 ClickHouseDialectHealer。
按照 Matt Pocock 的规范：
1. 模块应该是一个 Deep Module，外部仅暴露唯一的接缝接口: heal(sql: str) -> str
2. 内部消化所有 ClickHouse 别名遮蔽 (Code: 184)、非 ASCII 裸别名引号包裹、以及 Markdown/XML 脏标记。
3. 当前该模块尚未创建，该测试预期必须【报错/红灯 (RED)】！
"""
import pytest

def test_healer_module_exists_and_heals_shadowing_alias():
    # 尝试从预期的独立深模块中导入
    from app.core.protocol.clickhouse_healer import ClickHouseDialectHealer
    
    dirty_sql = "SELECT min(setl_time) AS setl_time FROM fqz_fymx_test WHERE setl_time >= '2023-01-01'"
    healed = ClickHouseDialectHealer.heal(dirty_sql)
    
    # 断言别名已被自愈重命名，避免 ClickHouse Code: 184 非法聚合遮蔽
    assert "min_setl_time" in healed or "setl_time >= '2023-01-01'" in healed
    assert "min(setl_time) AS setl_time" not in healed

def test_healer_handles_non_ascii_alias():
    from app.core.protocol.clickhouse_healer import ClickHouseDialectHealer
    
    raw_sql = "SELECT count(*) AS 费用总笔数 FROM fqz_fymx_test"
    healed = ClickHouseDialectHealer.heal(raw_sql)
    
    # 中文裸别名必须被包裹引号以防止语法解析崩溃
    assert 'AS "费用总笔数"' in healed or 'AS `费用总笔数`' in healed
