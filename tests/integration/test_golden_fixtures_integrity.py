import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from app.infra.db_conn import get_clickhouse_client

def test_golden_dataset_has_verifiable_cross_hospital_records():
    client = get_clickhouse_client()
    # 验证同一人同日跨机构就诊 (h_cnt >= 2) 存在且可查
    q = """
    SELECT 
        count(*) as cnt,
        round(sum(tot_fee), 2) as sum_amt
    FROM (
        SELECT 
            psn_no, 
            toDate(setl_time) as d, 
            count(DISTINCT fixmedins_name) as h_cnt,
            sum(medfee_sumamt) as tot_fee
        FROM fqz_gz_jzsj_all_ql
        GROUP BY psn_no, d
        HAVING h_cnt >= 2
    )
    """
    rows = client.query(q)
    row = rows[0] if isinstance(rows[0], dict) else {"cnt": rows[0][0], "sum_amt": rows[0][1]}
    cnt = int(row["cnt"])
    sum_amt = float(row["sum_amt"])
    assert cnt == 5, f"Expected 5 cross-hospital patient cases, got {cnt}"
    assert abs(sum_amt - 1581.64) < 0.05, f"Expected total fee 1581.64, got {sum_amt}"

def test_golden_dataset_has_100_percent_fund_pay_records():
    client = get_clickhouse_client()
    # 验证全额统筹支付 (fund_pay_sumamt = medfee_sumamt > 0)
    q = """
    SELECT 
        count(*) as cnt,
        round(sum(fund_pay_sumamt), 2) as sum_amt
    FROM fqz_gz_jzsj_all_ql
    WHERE fund_pay_sumamt = medfee_sumamt AND medfee_sumamt > 0
    """
    rows = client.query(q)
    row = rows[0] if isinstance(rows[0], dict) else {"cnt": rows[0][0], "sum_amt": rows[0][1]}
    cnt = int(row["cnt"])
    sum_amt = float(row["sum_amt"])
    assert cnt == 108, f"Expected 108 full-fund-pay records, got {cnt}"
    assert abs(sum_amt - 2390.40) < 0.05, f"Expected total fund pay 2390.40, got {sum_amt}"

if __name__ == "__main__":
    test_golden_dataset_has_verifiable_cross_hospital_records()
    test_golden_dataset_has_100_percent_fund_pay_records()
    print("ALL GOLDEN FIXTURE INTEGRITY TESTS PASSED!")
