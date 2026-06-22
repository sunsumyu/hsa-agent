from clickhouse_driver import Client

def check_tables():
    client = Client(host='127.0.0.1', port=9000)
    tables = [
        'fqz_ptzy_hosp', 
        'fqz_ztk_psn_yearly', 
        'fqz_gz_jzsj_all_ql',
        'fqz_all_yy_yd_1'
    ]
    
    results = {}
    for t in tables:
        try:
            count = client.execute(f"SELECT count(*) FROM default.{t}")
            results[t] = count[0][0]
        except Exception as e:
            results[t] = f"ERROR: {str(e)}"
    
    for t, res in results.items():
        print(f"{t}: {res}")

if __name__ == "__main__":
    check_tables()
