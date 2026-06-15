import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

sys.path.append(os.getcwd())
from app.infra.db_conn import get_clickhouse_client

def main():
    client = get_clickhouse_client()
    print("Checking default.fqz_fymx_test for 3-5s sequences of identical items...")
    
    # Let's query all records sorted by clinic and time
    sql = """
    SELECT 
        replace(setl_time, '\\t', '') as setl_time_str, 
        replace(fixmedins_code, '\\t', '') as fix_code, 
        replace(fixmedins_name, '\\t', '') as fix_name, 
        replace(psn_no, '\\t', '') as psn_no_clean,
        replace(psn_name, '\\t', '') as psn_name_clean,
        replace(hilist_name, '\\t', '') as hilist_name_clean,
        replace(setl_id, '\\t', '') as setl_id_clean
    FROM default.fqz_fymx_test
    ORDER BY fix_code, setl_time_str
    """
    rows = client.query(sql)
    print(f"Total rows: {len(rows)}")
    
    by_store = {}
    for r in rows:
        store = r['fix_code']
        if store not in by_store:
            by_store[store] = []
        by_store[store].append(r)
        
    found_any = False
    for store, records in by_store.items():
        if len(records) < 5:
            continue
            
        print(f"\nStore: {store} ({records[0]['fix_name']}) has {len(records)} records.")
        import datetime
        
        # We need to parse setl_time_str as datetime
        parsed_records = []
        for r in records:
            try:
                t = datetime.datetime.strptime(r['setl_time_str'], "%Y-%m-%d %H:%M:%S")
                r['parsed_time'] = t
                parsed_records.append(r)
            except Exception as e:
                # print(f"Error parsing time {repr(r['setl_time_str'])}: {e}")
                pass
                
        # Now find sequences of consecutive records with same hilist_name settled within <= 5s by different patients
        i = 0
        while i < len(parsed_records):
            seq = [parsed_records[i]]
            j = i + 1
            while j < len(parsed_records):
                last_rec = seq[-1]
                curr_rec = parsed_records[j]
                
                # Check interval
                diff = (curr_rec['parsed_time'] - last_rec['parsed_time']).total_seconds()
                
                # Check if same item, different patient, and interval between 3 and 5 seconds (or <= 5s)
                if 0 <= diff <= 5 and curr_rec['hilist_name_clean'] == last_rec['hilist_name_clean'] and curr_rec['psn_no_clean'] != last_rec['psn_no_clean']:
                    seq.append(curr_rec)
                    j += 1
                elif diff == 0 and curr_rec['hilist_name_clean'] == last_rec['hilist_name_clean'] and curr_rec['psn_no_clean'] == last_rec['psn_no_clean']:
                    # Duplicates or same patient multiple entries at same time, skip or allow?
                    j += 1
                else:
                    break
            
            if len(seq) >= 3:
                print(f"  🚨 Found sequence of length {len(seq)} starting at index {i}!")
                for r in seq:
                    print(f"    Patient: {r['psn_name_clean']} ({r['psn_no_clean']}) | Time: {r['setl_time_str']} | Item: {r['hilist_name_clean']}")
                found_any = True
                i = j
            else:
                i += 1
                
    if not found_any:
        print("\n❌ No sequence of 3+ records found in fqz_fymx_test.")

if __name__ == '__main__':
    main()
