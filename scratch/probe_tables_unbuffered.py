# -*- coding: utf-8 -*-
import os, sys, traceback
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def probe():
    client = get_clickhouse_client()
    
    print(">>> All Databases:", flush=True)
    try:
        res = client.query("SHOW DATABASES")
        for row in res:
            print(f"  - {row}", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)

    print("\n>>> All Tables in all databases:", flush=True)
    try:
        res = client.query("SELECT database, name FROM system.tables WHERE database NOT IN ('system', 'information_schema')")
        for row in res:
            print(f"  - {row}", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)

if __name__ == "__main__":
    probe()
