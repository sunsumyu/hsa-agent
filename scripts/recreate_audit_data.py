from clickhouse_driver import Client
import random
from datetime import datetime, timedelta

def recreate_and_seed():
    client = Client(host='127.0.0.1', port=9000)
    
    # 1. Drop existing table
    print("Dropping existing table fqz_all_yy_yd_1...")
    client.execute("DROP TABLE IF EXISTS default.fqz_all_yy_yd_1")
    
    # 2. Create table with correct schema (No nullable in keys for ClickHouse 26.x)
    print("Creating table fqz_all_yy_yd_1 with correct schema...")
    create_sql = """
    CREATE TABLE default.fqz_all_yy_yd_1 (
        fixmedins_code String,
        fixmedins_name String,
        admdvs String,
        medfee_sumamt Decimal(18, 2) DEFAULT 0,
        fund_pay_sumamt Decimal(18, 2) DEFAULT 0,
        setl_time DateTime
    ) ENGINE = MergeTree()
    PARTITION BY admdvs
    ORDER BY (fixmedins_code, setl_time)
    """
    client.execute(create_sql)
    print("Table created successfully.")

    # 3. Seed 100 rows for April 2026
    print("Seeding 100 rows for April 2026...")
    hospitals = [
        ("H001", "广州市第一人民医院"),
        ("H002", "中山大学附属第一医院"),
        ("H003", "南方医科大学南方医院"),
        ("H004", "广东省人民医院"),
        ("H005", "广州中医药大学第一附属医院")
    ]
    
    start_date = datetime(2026, 4, 1)
    rows = []
    
    for i in range(100):
        h_code, h_name = random.choice(hospitals)
        # Random time in April 2026
        dt = start_date + timedelta(days=random.randint(0, 29), hours=random.randint(8, 22), minutes=random.randint(0, 59))
        
        # Scenario: Some high risks (> 20,000)
        if i % 10 == 0:
            fee = random.uniform(20000, 80000)
            # High risk: 基金支付比例低 (e.g. 10%-40%) -> 自付比例高 (60%-90%)
            fund = fee * random.uniform(0.1, 0.4) 
        else:
            fee = random.uniform(100, 5000)
            fund = fee * random.uniform(0.6, 0.9)
        
        rows.append({
            "fixmedins_code": h_code,
            "fixmedins_name": h_name,
            "admdvs": "440100", # Guangzhou
            "medfee_sumamt": fee,
            "fund_pay_sumamt": fund,
            "setl_time": dt
        })


    insert_sql = "INSERT INTO default.fqz_all_yy_yd_1 (fixmedins_code, fixmedins_name, admdvs, medfee_sumamt, fund_pay_sumamt, setl_time) VALUES"
    client.execute(insert_sql, rows)
    print("Successfully seeded 100 rows.")

    # 4. Verify count
    count = client.execute("SELECT count(*) FROM default.fqz_all_yy_yd_1")[0][0]
    print(f"Final Row Count in fqz_all_yy_yd_1: {count}")

if __name__ == "__main__":
    recreate_and_seed()
