# -*- coding: utf-8 -*-
"""
Search for staff/doctor columns in ClickHouse
"""
import os, sys
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

def search_cols():
    client = get_clickhouse_client()
    for table in ["fqz_gz_jzsj_all_ql", "fqz_fymx_test"]:
        print("=" * 80)
        print(f"COLUMNS IN {table}:")
        print("=" * 80)
        try:
            res = client.query(f"DESCRIBE TABLE {table}")
            for row in res:
                name = row["name"].lower()
                # Check for keywords related to doctor, staff, operator, execute, etc.
                keywords = ["staff", "dr", "doc", "exec", "physician", "ys", "doctor", "oper", "comp", "time", "ocur"]
                if any(k in name for k in keywords):
                    print(f"  - {row['name']} ({row['type']})")
        except Exception as e:
            print(f"Failed to describe {table}: {e}")

if __name__ == "__main__":
    search_cols()
