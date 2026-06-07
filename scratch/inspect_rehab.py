import os, sys
sys.path.append(os.getcwd())
import clickhouse_driver

def inspect():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password='', database='default'
    )
    
    tables = ['fqz_gz_jzsj_all_ql', 'fqz_gz_jzsj_all_ql_clean', 'fqz_gz_jzsj_all_ql_fixed']
    for t in tables:
        print(f"\n=== Inspecting default.{t} ===")
        # Count non-empty values
        try:
            res = client.execute(
                f"SELECT count(), "
                f"countIf(chfpdr_name != '' AND chfpdr_name IS NOT NULL), "
                f"countIf(chfpdr_code != '' AND chfpdr_code IS NOT NULL), "
                f"countIf(adm_dept_name != '' AND adm_dept_name IS NOT NULL) "
                f"FROM default.{t}"
            )
            print(f"  Total rows: {res[0][0]}")
            print(f"  Non-empty chfpdr_name: {res[0][1]}")
            print(f"  Non-empty chfpdr_code: {res[0][2]}")
            print(f"  Non-empty adm_dept_name: {res[0][3]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    inspect()
