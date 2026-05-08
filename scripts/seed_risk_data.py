import clickhouse_connect
import random
from datetime import datetime, timedelta

def generate_risk_data():
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
    
    # Tables to populate
    # 1. fqz_all_yy_yd_1 (Settlement Detail)
    # 2. fqz_ptzy_hosp (Hospitalization Summary)
    # 3. fqz_ztk_psn_yearly (Patient Yearly Stats)

    client.command("TRUNCATE TABLE IF EXISTS default.fqz_all_yy_yd_1")
    client.command("TRUNCATE TABLE IF EXISTS default.fqz_ptzy_hosp")
    client.command("TRUNCATE TABLE IF EXISTS default.fqz_ztk_psn_yearly")

    hospitals = [
        ("H001", "广州市第一人民医院"),
        ("H002", "中山大学附属第一医院"),
        ("H003", "南方医科大学南方医院"),
        ("H004", "广东省人民医院"),
        ("H005", "广州中医药大学第一附属医院")
    ]
    
    start_date = datetime(2026, 4, 1)
    
    # 1. Normal Base Data (500 rows)
    print("Generating 500 normal rows...")
    normal_rows = []
    for _ in range(500):
        h_code, h_name = random.choice(hospitals)
        dt = start_date + timedelta(days=random.randint(0, 25), hours=random.randint(8, 20))
        fee = random.uniform(200, 5000)
        fund = fee * random.uniform(0.65, 0.85)
        normal_rows.append({
            "fixmedins_code": h_code, "fixmedins_name": h_name,
            "admdvs": "440100", "medfee_sumamt": fee, "fund_pay_sumamt": fund,
            "setl_time": dt
        })

    # 2. TRIGGER 1: Large Expenditure (> 100k)
    print("Triggering Rule 1: Large Expenditure...")
    extreme_rows = []
    for _ in range(5):
        h_code, h_name = random.choice(hospitals)
        dt = start_date + timedelta(days=random.randint(0, 20))
        fee = random.uniform(120000, 250000)
        fund = fee * 0.8
        extreme_rows.append({
            "fixmedins_code": h_code, "fixmedins_name": h_name,
            "admdvs": "440100", "medfee_sumamt": fee, "fund_pay_sumamt": fund,
            "setl_time": dt
        })
    
    # 3. TRIGGER 2: Split Hospitalization (same patient, 10 days apart)
    # Using local mapping to represent "same patient" in fqz_all_yy_yd_1 (simple table doesn't have psn_id, but the agent recognizes by sequence)
    print("Triggering Rule 2: Split Hospitalization...")
    split_rows = []
    patient_a_name = "张三 (可疑分解住院)"
    h_code, h_name = hospitals[0]
    # First discharge
    dt1 = datetime(2026, 4, 2, 10, 0)
    split_rows.append({
        "fixmedins_code": h_code, "fixmedins_name": h_name,
        "admdvs": "440100", "medfee_sumamt": 5500, "fund_pay_sumamt": 4000,
        "setl_time": dt1
    })
    # Second admission/settlement 8 days later
    dt2 = datetime(2026, 4, 10, 14, 0)
    split_rows.append({
        "fixmedins_code": h_code, "fixmedins_name": h_name,
        "admdvs": "440100", "medfee_sumamt": 4200, "fund_pay_sumamt": 3000,
        "setl_time": dt2
    })

    # 4. TRIGGER 3: High Self-Pay Ratio (> 60%)
    print("Triggering Rule 3: High Self-Pay Ratio...")
    self_pay_rows = []
    for _ in range(10):
        h_code, h_name = random.choice(hospitals)
        dt = start_date + timedelta(days=random.randint(0, 25))
        fee = random.uniform(10000, 20000)
        # Fund only pays 20% -> Self pay 80%
        fund = fee * 0.2 
        self_pay_rows.append({
            "fixmedins_code": h_code, "fixmedins_name": h_name,
            "admdvs": "440100", "medfee_sumamt": fee, "fund_pay_sumamt": fund,
            "setl_time": dt
        })

    # 5. TRIGGER 4: High-Frequency Shopping (in fqz_ztk_psn_yearly)
    print("Triggering Rule 4: High-Frequency Shopping (yearly stats table)...")
    frequency_rows = []
    frequency_rows.append({
        "setl_rq": "202604", "certno": "440100198001011234", "psn_name": "李四 (可疑进常客)",
        "admdvs": "440100", "provice_code": "440000",
        "jzcs": 15, "jzcs_zy": 5, "medfee_sumamt": 80000, "fund_pay_sumamt": 60000,
        "acct_pay": 5000, "cash_payamt": 15000, "ipt_days_hj": 20, "crt_time": datetime.now()
    })

    # 6. TRIGGER 5: Bed-Hanging (in fqz_ptzy_hosp)
    print("Triggering Rule 5: Bed-Hanging (long stay, low fee table)...")
    bed_hanging_rows = []
    bed_hanging_rows.append({
        "setl_rq": "202604", "fixmedins_code": "H005", "fixmedins_name": "广州中医药大学第一附属医院",
        "medinslv": "3", "medins_natu": "1", "provice_code": "440000", "admdvs": "440100",
        "medfee_sumamt": 800, "fund_pay_sumamt": 500, "acct_pay": 100, "cash_payamt": 200,
        "ipt_days_hj": 45, "crt_time": datetime.now() # 45 days for only 800 RMB
    })

    # Combine and Insert
    all_settlements = [[r['fixmedins_code'], r['fixmedins_name'], r['admdvs'], r['medfee_sumamt'], r['fund_pay_sumamt'], r['setl_time']] for r in (normal_rows + extreme_rows + split_rows + self_pay_rows)]
    client.insert('default.fqz_all_yy_yd_1', all_settlements, column_names=['fixmedins_code', 'fixmedins_name', 'admdvs', 'medfee_sumamt', 'fund_pay_sumamt', 'setl_time'])
    
    print(f"Total settlements inserted into fqz_all_yy_yd_1: {len(all_settlements)}")

    psn_data = [[r['setl_rq'], r['certno'], r['psn_name'], r['admdvs'], r['provice_code'], r['jzcs'], r['jzcs_zy'], r['medfee_sumamt'], r['fund_pay_sumamt'], r['acct_pay'], r['cash_payamt'], r['ipt_days_hj'], r['crt_time']] for r in frequency_rows]
    client.insert('default.fqz_ztk_psn_yearly', psn_data, column_names=['setl_rq', 'certno', 'psn_name', 'admdvs', 'provice_code', 'jzcs', 'jzcs_zy', 'medfee_sumamt', 'fund_pay_sumamt', 'acct_pay', 'cash_payamt', 'ipt_days_hj', 'crt_time'])
    print("Frequency anomaly row inserted.")

    hosp_data = [[r['setl_rq'], r['fixmedins_code'], r['fixmedins_name'], r['medinslv'], r['medins_natu'], r['provice_code'], r['admdvs'], r['medfee_sumamt'], r['fund_pay_sumamt'], r['acct_pay'], r['cash_payamt'], r['ipt_days_hj'], r['crt_time']] for r in bed_hanging_rows]
    client.insert('default.fqz_ptzy_hosp', hosp_data, column_names=['setl_rq', 'fixmedins_code', 'fixmedins_name', 'medinslv', 'medins_natu', 'provice_code', 'admdvs', 'medfee_sumamt', 'fund_pay_sumamt', 'acct_pay', 'cash_payamt', 'ipt_days_hj', 'crt_time'])
    print("Bed-hanging anomaly row inserted.")

if __name__ == "__main__":
    generate_risk_data()
