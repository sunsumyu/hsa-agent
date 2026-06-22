# -*- coding: utf-8 -*-
"""
QA-CUST-26 根因诊断 v2 - 原始 bytes 输出，绕开 Windows 控制台编码问题
"""
import sys, os
sys.path.append(os.getcwd())

import clickhouse_connect

# 直连，不走 app 层避免包装
host = os.getenv("CLICKHOUSE_HOST", "localhost")
port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
db   = os.getenv("CLICKHOUSE_DB", "default")
user = os.getenv("CLICKHOUSE_USER", "default")
pwd  = os.getenv("CLICKHOUSE_PASSWORD", "")

client = clickhouse_connect.get_client(host=host, port=port, database=db, username=user, password=pwd)

OUT = open("scratch/diag_cust26_result.txt", "w", encoding="utf-8", errors="replace")

def p(s):
    print(s)
    OUT.write(s + "\n")

def q(sql, label):
    p(f"\n{'='*60}")
    p(f"[{label}]")
    try:
        result = client.query(sql)
        rows = result.result_rows
        cols = result.column_names
        p(f"列名: {cols}")
        p(f"行数: {len(rows)}")
        for row in rows[:15]:
            line_parts = []
            for v in row:
                try:
                    line_parts.append(str(v))
                except:
                    line_parts.append(repr(v))
            p("  " + " | ".join(line_parts))
    except Exception as e:
        p(f"ERROR: {e}")

# 1. 总行数
q("SELECT count() FROM default.fqz_gz_jzsj_all_ql", "1-A jzsj总行数")
q("SELECT count() FROM default.fqz_fymx_test", "1-B fymx总行数")

# 2. med_type 分布
q("SELECT med_type, count() FROM default.fqz_gz_jzsj_all_ql GROUP BY med_type ORDER BY count() DESC LIMIT 10", "2-A jzsj med_type分布")
q("SELECT med_type, count() FROM default.fqz_fymx_test GROUP BY med_type ORDER BY count() DESC LIMIT 10", "2-B fymx med_type分布")

# 3. fixmedins_name 的 hex（原始字节）
q("""
SELECT hex(fixmedins_name) AS hex_val, length(fixmedins_name) AS byte_len
FROM default.fqz_gz_jzsj_all_ql LIMIT 5
""", "3-A jzsj fixmedins_name hex原始字节")

q("""
SELECT hex(fixmedins_name) AS hex_val, length(fixmedins_name) AS byte_len
FROM default.fqz_fymx_test LIMIT 5
""", "3-B fymx fixmedins_name hex原始字节")

# 4. setl_id 交集
q("""
SELECT count() 
FROM default.fqz_gz_jzsj_all_ql A
WHERE A.setl_id IN (SELECT setl_id FROM default.fqz_fymx_test LIMIT 10000)
""", "4 setl_id交集数量")

# 5. fymx 机构名 TOP10
q("""
SELECT fixmedins_name, count() cnt
FROM default.fqz_fymx_test
GROUP BY fixmedins_name
ORDER BY cnt DESC
LIMIT 10
""", "5-A fymx fixmedins_name TOP10")

# 6. fymx setl_time 类型和范围
q("""
SELECT 
    toTypeName(setl_time) AS t_type,
    min(setl_time) AS min_t,
    max(setl_time) AS max_t,
    count() AS cnt
FROM default.fqz_fymx_test
""", "6 fymx setl_time类型和范围")

q("""
SELECT 
    toTypeName(setl_time) AS t_type,
    min(setl_time) AS min_t,
    max(setl_time) AS max_t,
    count() AS cnt
FROM default.fqz_gz_jzsj_all_ql
""", "6-B jzsj setl_time类型和范围")

# 7. fymx 直接时序检测（修正 setl_time 类型问题用 toDateTime）
q("""
SELECT 
    toDate(toDateTime(setl_time)) AS setl_date,
    fixmedins_name,
    hilist_name,
    count(DISTINCT psn_no) AS patient_count,
    min(toDateTime(setl_time)) AS first_t,
    max(toDateTime(setl_time)) AS last_t,
    dateDiff('second', min(toDateTime(setl_time)), max(toDateTime(setl_time))) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, fixmedins_name, hilist_name
HAVING patient_count >= 5 AND span_seconds <= 120
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "7 fymx 时序批量刷单（直接查，不JOIN）")

# 8. jzsj 原始5条所有字段（hex方式）
q("""
SELECT 
    hex(psn_no) AS psn_hex,
    hex(fixmedins_name) AS fn_hex,
    hex(med_type) AS mt_hex,
    setl_time,
    medfee_sumamt
FROM default.fqz_gz_jzsj_all_ql LIMIT 5
""", "8 jzsj 原始hex 5条")

# 9. jzsj - 检查 fixmedins_name 是否为 GBK 编码
q("""
SELECT 
    convertCharset(fixmedins_name, 'GBK', 'UTF-8') AS decoded_name,
    length(fixmedins_name) AS len
FROM default.fqz_gz_jzsj_all_ql
LIMIT 5
""", "9 jzsj fixmedins_name GBK->UTF8解码尝试")

# 10. fymx 的 hilist_name 和 med_type 样本
q("""
SELECT psn_no, hilist_name, med_type, fixmedins_name, setl_time
FROM default.fqz_fymx_test
LIMIT 10
""", "10 fymx 原始10条完整字段")

OUT.close()
p("\n[诊断完毕，结果已写入 scratch/diag_cust26_result.txt]")
