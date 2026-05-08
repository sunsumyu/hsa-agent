import os
import clickhouse_connect
from dotenv import load_dotenv

def audit_schema_fields():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    port = int(os.getenv("CLICKHOUSE_PORT", 8123))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    databases = ["default", "fqz_hsa"]
    print(f"{'Database':<15} | {'Table':<30} | {'Field':<15} | {'Type':<15}")
    print("-" * 80)
    
    for db in databases:
        try:
            tables_res = client.query(f"SHOW TABLES FROM {db}")
            for t_row in tables_res.result_rows:
                table_name = t_row[0]
                if table_name.startswith(".inner"):
                    continue
                
                try:
                    cols_res = client.query(f"DESCRIBE TABLE {db}.{table_name}")
                    for c_row in cols_res.result_rows:
                        col_name = c_row[0]
                        col_type = c_row[1]
                        
                        # 重点搜索 psn_no, start_date, medfee_sumamt 等核心审计维度
                        if col_name.lower() in ["psn_no", "start_date", "med_type", "ipt_days"]:
                            print(f"{db:<15} | {table_name:<30} | {col_name:<15} | {col_type:<15}")
                except:
                    pass
        except Exception as e:
            print(f"Error accessing DB {db}: {e}")

if __name__ == "__main__":
    audit_schema_fields()
