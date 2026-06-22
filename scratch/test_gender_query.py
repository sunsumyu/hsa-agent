import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def run_query():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    query = """
        SELECT psn_name, gend, hilist_name, det_item_fee_sumamt 
        FROM default.fqz_fymx_test 
        WHERE trim(gend) = '1' AND (
            hilist_name LIKE '%妇%' 
            OR hilist_name LIKE '%产%' 
            OR hilist_name LIKE '%阴%' 
            OR hilist_name LIKE '%孕%' 
            OR hilist_name LIKE '%宫%' 
            OR hilist_name LIKE '%胎%'
        )
        LIMIT 10
    """
    try:
        res = client.execute(query)
        print(f"Query returned {len(res)} rows:")
        for row in res:
            # Let's decode or clean representation
            cleaned_row = []
            for item in row:
                if isinstance(item, str):
                    cleaned_row.append(item.replace('\t', '\\t'))
                else:
                    cleaned_row.append(item)
            print(f"  - {cleaned_row}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_query()
