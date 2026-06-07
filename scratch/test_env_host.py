import os, sys
sys.path.append(os.getcwd())

from dotenv import load_dotenv
import clickhouse_driver

def test_conn():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST")
    db = os.getenv("CLICKHOUSE_DB")
    print(f"Loaded from .env: host={host}, db={db}")
    
    print(f"Testing direct connection to host {host} on port 9000...", flush=True)
    try:
        client = clickhouse_driver.Client(
            host=host, port=9000, user='default', password='', database=db,
            connect_timeout=3
        )
        res = client.execute("SELECT 1")
        print(f"Connection to remote host {host} succeeded: {res}")
    except Exception as e:
        print(f"Connection to remote host {host} failed: {e}")

    print("\nTesting direct connection to localhost:9000 with db='default'...", flush=True)
    try:
        client = clickhouse_driver.Client(
            host='localhost', port=9000, user='default', password='', database='default',
            connect_timeout=3
        )
        res = client.execute("SELECT 1")
        print(f"Connection to localhost:9000 (db=default) succeeded: {res}")
    except Exception as e:
        print(f"Connection to localhost:9000 (db=default) failed: {e}")

if __name__ == "__main__":
    test_conn()
