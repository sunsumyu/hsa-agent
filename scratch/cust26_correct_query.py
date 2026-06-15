# -*- coding: utf-8 -*-
"""
QA-CUST-26 正确查询：直接在 fqz_fymx_test 查时序批量刷单
关键修正：
1. 只查 fqz_fymx_test，不 JOIN jzsj（两表 setl_id 完全不重叠）
2. med_type 是数字编码（11=普通门诊, 21=住院, 53_04=特病门诊等），11 是门诊
3. setl_time 是带\t的 String 类型，要用 trim + parseDateTimeBestEffort 处理
4. 机构名含 "卫生" 关键词即可匹配卫生院/卫生室
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

OUT = open("scratch/cust26_correct_query_result.txt", "w", encoding="utf-8", errors="replace")

def p(s):
    print(s)
    OUT.write(s + "\n")

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
            line_parts = [str(v) for v in row]
            p("  " + " | ".join(line_parts))
        if len(rows) == 0:
            p("  >>> 查询结果为空 <<<")
    except Exception as e:
        p(f"ERROR: {e}")

# =====================================================================
# Step 1: 确认 med_type=11 是门诊，看样本数据
# =====================================================================
q("""
SELECT med_type, count() cnt,
       min(trim(setl_time)) AS min_t,
       max(trim(setl_time)) AS max_t
FROM default.fqz_fymx_test
GROUP BY med_type
ORDER BY cnt DESC
""", "Step1: med_type完整分布（含时间范围）")

# =====================================================================
# Step 2: 卫生院/卫生室机构数据量
# =====================================================================
q("""
SELECT 
    fixmedins_name,
    med_type,
    count() cnt,
    count(DISTINCT psn_no) patient_cnt
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
GROUP BY fixmedins_name, med_type
ORDER BY cnt DESC
LIMIT 20
""", "Step2: 卫生院/卫生室机构统计")

# =====================================================================
# Step 3: 时序批量刷单查询（核心逻辑）
# 同一机构、同一天、同一药品/项目，>=5个不同患者在60秒内结算
# setl_time 是 String+\t，用 parseDateTimeBestEffort(trim(setl_time))
# =====================================================================
q("""
SELECT 
    toDate(parseDateTimeBestEffort(trim(setl_time))) AS setl_date,
    fixmedins_name,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    min(parseDateTimeBestEffort(trim(setl_time))) AS first_settle,
    max(parseDateTimeBestEffort(trim(setl_time))) AS last_settle,
    dateDiff('second',
        min(parseDateTimeBestEffort(trim(setl_time))),
        max(parseDateTimeBestEffort(trim(setl_time)))
    ) AS span_seconds,
    groupArray(trim(psn_no)) AS psn_list
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
GROUP BY setl_date, fixmedins_name, item_name
HAVING patient_count >= 5 AND span_seconds <= 60
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 30
""", "Step3: 卫生院/室 时序批量刷单（>=5人/60秒内/同药品）")

# =====================================================================
# Step 4: 放宽条件，>=3人，300秒内
# =====================================================================
q("""
SELECT 
    toDate(parseDateTimeBestEffort(trim(setl_time))) AS setl_date,
    fixmedins_name,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second',
        min(parseDateTimeBestEffort(trim(setl_time))),
        max(parseDateTimeBestEffort(trim(setl_time)))
    ) AS span_seconds,
    round(patient_count / greatest(span_seconds, 1) * 60, 2) AS patients_per_minute
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
GROUP BY setl_date, fixmedins_name, item_name
HAVING patient_count >= 3 AND span_seconds <= 300
ORDER BY patients_per_minute DESC, patient_count DESC
LIMIT 30
""", "Step4: 宽松条件（>=3人/5分钟内），计算每分钟结算人数")

# =====================================================================
# Step 5: 全库（不限机构类型）时序异常，>=10人，300秒内
# =====================================================================
q("""
SELECT 
    toDate(parseDateTimeBestEffort(trim(setl_time))) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second',
        min(parseDateTimeBestEffort(trim(setl_time))),
        max(parseDateTimeBestEffort(trim(setl_time)))
    ) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 10 AND span_seconds <= 300
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "Step5: 全库 时序异常（>=10人/5分钟内同药品）")

# =====================================================================
# Step 6: 全库最极端的批量刷单案例，不限时间窗
# =====================================================================
q("""
SELECT 
    toDate(parseDateTimeBestEffort(trim(setl_time))) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second',
        min(parseDateTimeBestEffort(trim(setl_time))),
        max(parseDateTimeBestEffort(trim(setl_time)))
    ) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 5
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "Step6: 全库 同天同药同机构 >=5人 TOP20（最极端案例）")

OUT.close()
p("\n[完成，结果写入 scratch/cust26_correct_query_result.txt]")
