from app.tools import get_clickhouse_client

client = get_clickhouse_client()

# 查所有表名和行数
tables_q = client.query("SELECT table, sum(rows) as total_rows FROM system.parts WHERE database='default' GROUP BY table ORDER BY total_rows DESC")
print("=== 所有表及行数 ===")
for row in tables_q.result_rows:
    print(f"  {row[0]}: {row[1]:,} 行")
