import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def list_items():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    query = """
        SELECT hilist_name, count() 
        FROM default.fqz_fymx_test 
        GROUP BY hilist_name 
        ORDER BY count() DESC
    """
    try:
        res = client.execute(query)
        print(f"Total distinct items: {len(res)}")
        for row in res[:50]:
            name = row[0].replace('\t', '\\t')
            print(f"  - {name}: {row[1]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_items()
