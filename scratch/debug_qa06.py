from app.db_conn import get_clickhouse_client

def test_template_sql():
    client = get_clickhouse_client()
    # Exact SQL from AuditRuleEngine.TEMPLATES["CROSS_HOSPITAL_OVERLAP"]
    query = """
        SELECT
            psn_no,
            toDate(setl_time)              AS setl_date,
            count(DISTINCT fixmedins_code) AS hospital_count,
            groupArray(fixmedins_name)     AS hospitals,
            sum(medfee_sumamt)             AS total_amount
        FROM fqz_gz_jzsj_all_ql
        WHERE toYear(toDateTime(setl_time)) = 2024
        GROUP BY psn_no, setl_date
        HAVING hospital_count > 1
        ORDER BY total_amount DESC
        LIMIT 50
    """
    print(f"RUNNING TEMPLATE SQL...")
    res = client.query(query)
    if not res.result_set:
        print("RESULT IS EMPTY!")
    else:
        print(f"SUCCESS! FOUND {len(res.result_set)} RECORDS.")
        print(f"SAMPLE: {res.result_set[0]}")

if __name__ == "__main__":
    test_template_sql()
