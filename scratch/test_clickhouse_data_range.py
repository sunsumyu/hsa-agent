import os
import sys

# Reconfigure stdout to use UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.infra.db_conn import get_clickhouse_client

def test_data_range():
    print(">>> Connecting to ClickHouse...")
    try:
        client = get_clickhouse_client()
        print("Connection succeeded!")
        
        # Show tables
        print("\n>>> Tables in database:")
        tables = client.query("SHOW TABLES")
        for idx, table in enumerate(tables):
            print(f"  {idx + 1}. {table.get('name', table.get('table', table))}")
            
        # Inspect fqz_gz_jzsj_all_ql
        print("\n>>> Querying fqz_gz_jzsj_all_ql...")
        ql_info = client.query("SELECT COUNT() as cnt, MIN(setl_time) as min_time, MAX(setl_time) as max_time FROM fqz_gz_jzsj_all_ql")
        print(f"Result for fqz_gz_jzsj_all_ql: {ql_info}")
        
        # Inspect fqz_fymx_test
        print("\n>>> Querying fqz_fymx_test...")
        try:
            fymx_info = client.query("SELECT COUNT() as cnt, MIN(fee_ocur_time) as min_time, MAX(fee_ocur_time) as max_time FROM fqz_fymx_test")
            print(f"Result for fqz_fymx_test: {fymx_info}")
        except Exception as e:
            print(f"Failed to query fqz_fymx_test: {e}")
            
        # Get sample rows from fqz_gz_jzsj_all_ql
        print("\n>>> Sample rows from fqz_gz_jzsj_all_ql (first 3 rows):")
        sample_rows = client.query("SELECT setl_id, psn_no, setl_time, medfee_sumamt FROM fqz_gz_jzsj_all_ql LIMIT 3")
        for r in sample_rows:
            print(r)
            
    except Exception as e:
        print(f"Error during query: {e}")

if __name__ == "__main__":
    test_data_range()
