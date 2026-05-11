from app.db_conn import get_clickhouse_client
import json

def check_schema():
    client = get_clickhouse_client()
    try:
        # 1. 检查主表结构
        res = client.query("DESCRIBE TABLE fqz_gz_jzsj_all_ql")
        columns = [row[0] for row in res.result_rows]
        
        # 2. 检查系统表中所有包含 'dept' 或 'department' 的列
        res_system = client.query("SELECT table, name FROM system.columns WHERE name LIKE '%dept%' OR name LIKE '%department%'")
        matches = [{"table": row[0], "column": row[1]} for row in res_system.result_rows]
        
        with open("e:/chain/hsa-agent-python/artifacts/schema_check.json", "w", encoding="utf-8") as f:
            json.dump({
                "main_table_columns": columns,
                "potential_matches": matches
            }, f, ensure_ascii=False, indent=2)
        print("Schema check completed and saved to artifacts/schema_check.json")
    except Exception as e:
        with open("e:/chain/hsa-agent-python/artifacts/schema_check.json", "w", encoding="utf-8") as f:
            json.dump({"error": str(e)}, f)
        print(f"Error during schema check: {e}")

if __name__ == "__main__":
    check_schema()
