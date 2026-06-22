# -*- coding: utf-8 -*-
"""
Show ClickHouse DDL
"""
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def show_ddl():
    client = get_clickhouse_client()
    for table in ["fqz_gz_jzsj_all_ql", "fqz_fymx_test"]:
        print("=" * 80)
        print(f"COLUMNS IN {table}:")
        print("=" * 80)
        try:
            res = client.query(f"DESCRIBE TABLE {table}")
            for row in res:
                # row is a dict, clickhouse DESCRIBE usually has keys like 'name', 'type'
                print(f"  - {row}")
        except Exception as e:
            print(f"Failed to describe {table}: {e}")

if __name__ == "__main__":
    show_ddl()
