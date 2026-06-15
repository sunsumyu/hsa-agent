import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import os
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    print("Fetching unique settlement records...")
    
    # Query distinct setl_time, fixmedins_code, psn_no
    sql = """
    SELECT DISTINCT 
        setl_time, 
        fixmedins_code, 
        fixmedins_name, 
        psn_no,
        psn_name
    FROM fqz_gz_jzsj_all_ql
    ORDER BY fixmedins_code, setl_time
    """
    rows = client.query(sql)
    print(f"Total unique records: {len(rows)}")
    
    # Group by store
    by_store = {}
    for r in rows:
        store = r['fixmedins_code']
        if store not in by_store:
            by_store[store] = []
        by_store[store].append(r)
        
    # Check sequences of <= 5 seconds diff
    found_any = False
    for store, records in by_store.items():
        if len(records) < 10:
            continue
            
        print(f"\nStore: {store} (Name: {repr(records[0]['fixmedins_name'])}) has {len(records)} unique records.")
        
        # Check sliding window of 10 consecutive records
        for i in range(len(records) - 9):
            window = records[i:i+10]
            
            # Check if all adjacent records in window are within 3-5 seconds (or <= 5 seconds)
            is_match = True
            diffs = []
            for j in range(9):
                t1 = window[j]['setl_time']
                t2 = window[j+1]['setl_time']
                diff = (t2 - t1).total_seconds()
                diffs.append(diff)
                
                # Check if interval is within 3-5 seconds (or <= 5 seconds)
                if not (0 <= diff <= 5):
                    is_match = False
                    break
                    
            if is_match:
                print(f"  🚨 Found match starting at index {i}!")
                print(f"  Times: {[r['setl_time'].strftime('%H:%M:%S') for r in window]}")
                print(f"  Diffs: {diffs}")
                print(f"  Patients: {[r['psn_name'] for r in window]}")
                found_any = True
                
    if not found_any:
        print("\n❌ No second-level automated billing sequences found in the unique records.")

if __name__ == "__main__":
    main()
