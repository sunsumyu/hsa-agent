import os, sys
sys.path.append(os.getcwd())

import clickhouse_driver

def run_query():
    client = clickhouse_driver.Client(
        host='localhost', port=9000, user='default', password=''
    )
    
    # Let's try different strip/replace methods in ClickHouse
    query1 = """
        SELECT count() 
        FROM default.fqz_fymx_test 
        WHERE trim(BOTH ' \t\r\n' FROM gend) = '1'
    """
    
    query2 = """
        SELECT count() 
        FROM default.fqz_fymx_test 
        WHERE replace(gend, '\t', '') = '1'
    """
    
    try:
        c1 = client.execute(query1)[0][0]
        print(f"Query 1 (trim BOTH): {c1} rows")
    except Exception as e:
        print(f"Query 1 failed: {e}")
        
    try:
        c2 = client.execute(query2)[0][0]
        print(f"Query 2 (replace): {c2} rows")
    except Exception as e:
        print(f"Query 2 failed: {e}")

    # If successful, let's query the actual conflict rows
    query3 = """
        SELECT psn_name, gend, hilist_name, det_item_fee_sumamt 
        FROM default.fqz_fymx_test 
        WHERE replace(gend, '\t', '') = '1' AND (
            replace(hilist_name, '\t', '') LIKE '%妇%' 
            OR replace(hilist_name, '\t', '') LIKE '%产%' 
            OR replace(hilist_name, '\t', '') LIKE '%阴%' 
            OR replace(hilist_name, '\t', '') LIKE '%孕%' 
            OR replace(hilist_name, '\t', '') LIKE '%宫%' 
            OR replace(hilist_name, '\t', '') LIKE '%胎%'
        )
        LIMIT 5
    """
    try:
        res = client.execute(query3)
        print(f"Conflict query returned {len(res)} rows:")
        for row in res:
            p_name = row[0].replace('\t', '')
            g = row[1].replace('\t', '')
            h_name = row[2].replace('\t', '')
            # Clean display encoding
            try:
                p_name = bytes(p_name, 'utf-8').decode('utf-8')
                h_name = bytes(h_name, 'utf-8').decode('utf-8')
            except Exception:
                pass
            print(f"  - Name: {repr(p_name)} | Gend: {repr(g)} | Item: {repr(h_name)} | Fee: {row[3]}")
    except Exception as e:
        print(f"Conflict query failed: {e}")

if __name__ == "__main__":
    run_query()
 Maroon = True
