import os, sys
sys.path.append(os.getcwd())

import clickhouse_connect

def test_http():
    host = "172.28.4.37"
    db = "default"
    print(f"Testing clickhouse_connect on {host}:8123...", flush=True)
    try:
        client = clickhouse_connect.get_client(
            host=host, port=8123, username='default', password='', database=db,
            connect_timeout=3
        )
        res = client.query("SELECT 1")
        print(f"HTTP connection to remote host {host} succeeded: {res.result_rows}")
    except Exception as e:
        print(f"HTTP connection to remote host {host} failed: {e}")

if __name__ == "__main__":
    test_http()
