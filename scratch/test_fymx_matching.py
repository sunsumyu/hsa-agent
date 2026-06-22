import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    print("Querying IDs from fqz_fymx_test...")
    rows = client.query("SELECT setl_id, setl_time FROM fqz_fymx_test WHERE setl_id LIKE '520100G%' AND setl_time LIKE '2024%' LIMIT 10")
    print(f"Found {len(rows)} matching 520100G in fqz_fymx_test:")
    for r in rows:
        raw_id = r['setl_id']
        clean_id = raw_id.replace('\t', '').strip()
        print(f"  Raw: {repr(raw_id)} | Cleaned: {repr(clean_id)} | setl_time: {repr(r['setl_time'])}")
        
        # Check in fqz_gz_jzsj_all_ql
        match = client.query(f"SELECT setl_id, setl_time FROM fqz_gz_jzsj_all_ql WHERE setl_id = '{clean_id}'")
        print(f"    Match in fqz_gz_jzsj_all_ql: {match}")

if __name__ == "__main__":
    main()
