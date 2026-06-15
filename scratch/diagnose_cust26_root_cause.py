# -*- coding: utf-8 -*-
"""
QA-CUST-26 根因诊断脚本
逐层验证为什么乡镇卫生院/村卫生室时序批量刷单查询返回0条
"""
import sys, os
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client

client = get_clickhouse_client()

def q(sql, label=""):
    print(f"\n{'='*60}")
    print(f"[{label}]")
    print(f"SQL: {sql}")
    print("-"*60)
    try:
        res = client.query(sql)
        rows = list(res)
        print(f"行数: {len(rows)}")
        for r in rows[:10]:
            # 安全打印，处理乱码
            safe = []
            for v in r:
                try:
                    safe.append(str(v).encode('utf-8', errors='replace').decode('utf-8'))
                except:
                    safe.append(repr(v))
            print("  ", safe)
    except Exception as e:
        print(f"ERROR: {e}")


# ===================== 第1层：基础表状况 =====================
q("SELECT count() FROM default.fqz_gz_jzsj_all_ql", "1-A jzsj总行数")
q("SELECT count() FROM default.fqz_fymx_test", "1-B fymx总行数")

# ===================== 第2层：med_type 分布 =====================
q("SELECT med_type, count() FROM default.fqz_gz_jzsj_all_ql GROUP BY med_type ORDER BY count() DESC LIMIT 10", "2 jzsj med_type分布")
q("SELECT med_type, count() FROM default.fqz_fymx_test GROUP BY med_type ORDER BY count() DESC LIMIT 10", "2 fymx med_type分布")

# ===================== 第3层：fixmedins_name 样本（原始hex） =====================
q("""
SELECT 
    fixmedins_name,
    hex(fixmedins_name) AS hex_val,
    length(fixmedins_name) AS len
FROM default.fqz_gz_jzsj_all_ql
LIMIT 5
""", "3-A jzsj fixmedins_name 样本(含hex)")

q("""
SELECT 
    fixmedins_name,
    hex(fixmedins_name) AS hex_val,
    length(fixmedins_name) AS len
FROM default.fqz_fymx_test
LIMIT 5
""", "3-B fymx fixmedins_name 样本(含hex)")

# ===================== 第4层：setl_id 交集 =====================
q("""
SELECT count() 
FROM default.fqz_gz_jzsj_all_ql A
WHERE A.setl_id IN (SELECT setl_id FROM default.fqz_fymx_test LIMIT 10000)
""", "4 setl_id交集行数（fymx前10000条）")

# ===================== 第5层：fymx 中是否有乡镇/村关键词 =====================
q("SELECT count() FROM default.fqz_fymx_test WHERE fixmedins_name LIKE '%卫生%'", "5-A fymx 含'卫生'的机构数")
q("SELECT count() FROM default.fqz_fymx_test WHERE fixmedins_name LIKE '%乡镇%'", "5-B fymx 含'乡镇'")
q("SELECT count() FROM default.fqz_fymx_test WHERE fixmedins_name LIKE '%卫生室%'", "5-C fymx 含'卫生室'")

q("""
SELECT fixmedins_name, count() cnt
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
GROUP BY fixmedins_name
ORDER BY cnt DESC
LIMIT 10
""", "5-D fymx 含卫生的机构汇总")

# ===================== 第6层：fymx 的时序分析（核心场景） =====================
q("""
SELECT count() 
FROM default.fqz_fymx_test
WHERE setl_time >= '2024-01-01'
""", "6-A fymx 2024年数据量")

# 直接在 fymx 上找时序批量结算（绕开 jzsj 表）
q("""
SELECT 
    toDate(setl_time) AS setl_date,
    fixmedins_name,
    hilist_name,
    count(DISTINCT psn_no) AS patient_count,
    min(setl_time) AS first_t,
    max(setl_time) AS last_t,
    dateDiff('second', min(setl_time), max(setl_time)) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, fixmedins_name, hilist_name
HAVING 
    patient_count >= 5
    AND span_seconds <= 60
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 20
""", "6-B fymx 直接时序批量刷单查询（绕开JOIN）")

# ===================== 第7层：jzsj fixmedins_name 是否有可用的中文 =====================
q("""
SELECT 
    fixmedins_name,
    count() cnt
FROM default.fqz_gz_jzsj_all_ql
GROUP BY fixmedins_name
ORDER BY cnt DESC
LIMIT 5
""", "7 jzsj 机构名TOP5（看是否有中文）")

# ===================== 第8层：jzsj 原始样本5条 =====================
q("""
SELECT psn_no, fixmedins_name, fixmedins_code, med_type, setl_time, medfee_sumamt
FROM default.fqz_gz_jzsj_all_ql
LIMIT 5
""", "8 jzsj 原始样本5条")

print("\n\n[诊断完毕]")
