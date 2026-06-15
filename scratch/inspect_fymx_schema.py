# -*- coding: utf-8 -*-
"""
为 QA-CUST-26 向 fqz_fymx_test 插入模拟批量刷单数据
场景：正安县庙塘镇卫生院在同一天，连续12个不同患者，
     每隔4秒结算一次"益母草颗粒"，模拟村医流水线套现
"""
import sys, os
sys.path.append(os.getcwd())

import clickhouse_connect
from datetime import datetime, timedelta

host = os.getenv("CLICKHOUSE_HOST", "localhost")
port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
db   = os.getenv("CLICKHOUSE_DB", "default")
user = os.getenv("CLICKHOUSE_USER", "default")
pwd  = os.getenv("CLICKHOUSE_PASSWORD", "")
client = clickhouse_connect.get_client(host=host, port=port, database=db, username=user, password=pwd)

# 先查一条现有记录，了解 fqz_fymx_test 的字段结构
print("=== 查询表结构 ===")
res = client.query("DESCRIBE TABLE default.fqz_fymx_test")
cols = [(r[0], r[1]) for r in res.result_rows]
print("列名 | 类型")
for c, t in cols:
    print(f"  {c} | {t}")

print("\n=== 查询一条样本数据 ===")
res2 = client.query("SELECT * FROM default.fqz_fymx_test LIMIT 1")
print("列名:", res2.column_names)
print("数据:", res2.result_rows[0] if res2.result_rows else "空")

# 确认表是否支持 INSERT（MergeTree 引擎）
print("\n=== 查询表引擎 ===")
res3 = client.query("""
SELECT engine, create_table_query 
FROM system.tables 
WHERE name = 'fqz_fymx_test' AND database = 'default'
""")
for r in res3.result_rows:
    print(f"引擎: {r[0]}")
    print(f"建表语句:\n{r[1][:500]}")
