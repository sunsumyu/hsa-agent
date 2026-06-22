import os, sys
sys.path.append(os.getcwd())
import clickhouse_driver

def inspect():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password='', database='default'
    )
    
    print("=== DDL for fqz_gz_jzsj_all_ql ===")
    for row in client.execute("DESCRIBE TABLE default.fqz_gz_jzsj_all_ql"):
        print(f"  {row[0]}: {row[1]}")
        
    print("\n=== DDL for fqz_fymx_test ===")
    for row in client.execute("DESCRIBE TABLE default.fqz_fymx_test"):
        print(f"  {row[0]}: {row[1]}")

    print("\n=== Sample row from fqz_gz_jzsj_all_ql ===")
    cols = [c[0] for c in client.execute("DESCRIBE TABLE default.fqz_gz_jzsj_all_ql")]
    row = client.execute("SELECT * FROM default.fqz_gz_jzsj_all_ql LIMIT 1")[0]
    for c, v in zip(cols, row):
        if v:
            print(f"  {c}: {v}")

    print("\n=== Sample row from fqz_fymx_test ===")
    cols2 = [c[0] for c in client.execute("DESCRIBE TABLE default.fqz_fymx_test")]
    row2 = client.execute("SELECT * FROM default.fqz_fymx_test LIMIT 1")[0]
    for c, v in zip(cols2, row2):
        if v:
            print(f"  {c}: {v}")

if __name__ == "__main__":
    inspect()
