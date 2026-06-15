# -*- coding: utf-8 -*-
"""
QA-CUST-26 正确查询 v3
关键修正：setl_time 是 String + \t 尾，必须先 substring(trim(x),1,19) 再 toDateTime
"""
import sys, os
sys.path.append(os.getcwd())
import clickhouse_connect

host = os.getenv("CLICKHOUSE_HOST", "localhost")
port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
db   = os.getenv("CLICKHOUSE_DB", "default")
user = os.getenv("CLICKHOUSE_USER", "default")
pwd  = os.getenv("CLICKHOUSE_PASSWORD", "")
client = clickhouse_connect.get_client(host=host, port=port, database=db, username=user, password=pwd)

def p(s):
    print(s)

def q(sql, label):
    p(f"\n{'='*70}")
    p(f"[{label}]")
    try:
        result = client.query(sql)
        rows = result.result_rows
        cols = result.column_names
        p(f"列名: {cols}")
        p(f"命中行数: {len(rows)}")
        for row in rows[:30]:
            p("  " + " | ".join(str(v) for v in row))
        if len(rows) == 0:
            p("  >>> 空 <<<")
    except Exception as e:
        p(f"ERROR: {e}")

# 关键：用 toDateTime(substring(trim(setl_time), 1, 19)) 处理带\t的字符串
FIX_DT = "toDateTime(substring(trim(setl_time), 1, 19))"

# Step1: 验证时间转换是否正常
q(f"""
SELECT 
    setl_time AS raw,
    {FIX_DT} AS dt_fixed,
    length(setl_time) AS raw_len
FROM default.fqz_fymx_test
LIMIT 5
""", "Step1: 验证时间转换")

# Step2: 时序批量刷单 >=5人/60秒
q(f"""
SELECT 
    toDate({FIX_DT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    min({FIX_DT}) AS first_settle,
    max({FIX_DT}) AS last_settle,
    dateDiff('second', min({FIX_DT}), max({FIX_DT})) AS span_seconds
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 5 AND span_seconds <= 60
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "Step2: 卫生院/室 >=5人 60秒内同药品批量结算")

# Step3: 放宽 >=3人/300秒
q(f"""
SELECT 
    toDate({FIX_DT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second', min({FIX_DT}), max({FIX_DT})) AS span_seconds,
    round(count(DISTINCT trim(psn_no)) / greatest(dateDiff('second', min({FIX_DT}), max({FIX_DT})), 1) * 60, 2) AS per_min
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 3 AND span_seconds <= 300
ORDER BY per_min DESC, patient_count DESC
LIMIT 20
""", "Step3: 卫生院/室 >=3人 5分钟内，按每分钟人数排序")

# Step4: 全库（不限机构）>=10人/300秒  
q(f"""
SELECT 
    toDate({FIX_DT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second', min({FIX_DT}), max({FIX_DT})) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 10 AND span_seconds <= 300
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "Step4: 全库 >=10人/5分钟 时序异常")

# Step5: 全库最多人数的同天同药同机构TOP20
q(f"""
SELECT 
    toDate({FIX_DT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second', min({FIX_DT}), max({FIX_DT})) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 5
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "Step5: 全库 同天同药同机构 >=5人 TOP20")

p("\n[完成]")
