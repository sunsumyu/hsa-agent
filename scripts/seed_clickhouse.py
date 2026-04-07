from clickhouse_driver import Client
import random
from datetime import datetime, timedelta

def seed_data():
    # Use port 9000 for Native protocol
    client = Client(host='127.0.0.1', port=9000)
    
    # Check if table exists
    try:
        # Check table under 'default' database
        client.execute("SELECT count(*) FROM default.fqz_all_yy_yd_1")
    except Exception as e:
        print(f"Error checking table: {e}")
        return

    # Dummy hospitals
    hospitals = [
        ("H001", "广州市第一人民医院"),
        ("H002", "中山大学附属第一医院"),
        ("H003", "南方医科大学南方医院"),
        ("H004", "广东省人民医院")
    ]
    
    # Current month: April 2026
    start_date = datetime(2026, 4, 1)
    
    rows = []
    for i in range(50):
        hosp_code, hosp_name = random.choice(hospitals)
        # Random date in April
        setl_time = start_date + timedelta(days=random.randint(0, 29), hours=random.randint(8, 20))
        
        # Random fees. Some very high to trigger audit interest
        medfee = random.uniform(100, 50000)
        fund_pay = medfee * random.uniform(0.7, 0.9)
        
        rows.append({
            "fixmedins_code": hosp_code,
            "fixmedins_name": hosp_name,
            "admdvs": "440100",
            "medfee_sumamt": medfee,
            "fund_pay_sumamt": fund_pay,
            "setl_time": setl_time
        })

    # Insert data
    sql = "INSERT INTO default.fqz_all_yy_yd (fixmedins_code, fixmedins_name, admdvs, medfee_sumamt, fund_pay_sumamt, setl_time) VALUES"
    try:
        client.execute(sql, rows)
        print(f"Successfully seeded 50 rows into default.fqz_all_yy_yd.")
    except Exception as e:
        print(f"Error inserting data: {e}")

if __name__ == "__main__":
    seed_data()
