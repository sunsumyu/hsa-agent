# -*- coding: utf-8 -*-
"""
为 QA-CUST-26 向 fqz_fymx_test 插入模拟批量刷单数据

场景1: 正安县庙塘镇卫生院，连续12个患者，每隔4秒结算一次"益母草颗粒"（秒级流水线刷单）
场景2: 威宁县哲觉镇卫生院，连续10个患者，每隔5秒结算"布洛芬缓释胶囊"
"""
import sys, os
sys.path.append(os.getcwd())

import clickhouse_connect
from datetime import datetime, timedelta

host = os.getenv("CLICKHOUSE_HOST", "localhost")
port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
db   = os.getenv("CLICKHOUSE_DB", "default")
user = os.getenv("CLICKHOUSE_USER", "default")
pwd  = os.getenv("CLICKHOUSE_PASSWORD", "")
client = clickhouse_connect.get_client(host=host, port=port, database=db, username=user, password=pwd)

# 场景1：正安县庙塘镇卫生院 12人×4秒 批量刷单
BASE_TIME_1 = datetime(2024, 3, 15, 22, 30, 0)  # 晚上10:30（村医收卡套现典型时间）
INSTITUTION_1 = "正安县庙塘镇卫生院\t"
ITEM_NAME_1 = "益母草颗粒\t"
ITEM_CODE_1 = "ZD01BAY0318010302251\t"
INST_CODE_1 = "H52030501001\t"

rows_1 = []
for i in range(12):
    t = BASE_TIME_1 + timedelta(seconds=i*4)
    t_str = t.strftime("%Y-%m-%d %H:%M:%S") + "\t"
    setl_id = f"QA26MOCK0001{i:04d}\t"
    psn_no = f"5200000200000000300{i+1:07d}\t"
    rows_1.append((
        "贵州省\t",           # prv_name
        "遵义市\t",           # city_name
        "正安县\t",           # admdvs_name
        psn_no,               # psn_no
        f"患者{i+1:03d}\t",   # psn_name
        f"52032319820{i+1:02d}121{i:03d}\t",  # certno
        psn_no,               # emp_no
        f"正安庙塘村医李某\t", # emp_name
        "15\t",               # emp_type
        "2\t",                # gend
        "2\t",                # cert_gend
        35 + i,               # age
        "390\t",              # insutype
        "11\t",               # med_type = 门诊统筹
        "15\t",               # psn_type
        "520300\t",           # insu_admdvs
        setl_id,              # setl_id
        "2024-03-15 00:00:00\t",  # begndate
        "2024-03-15 00:00:00\t",  # enddate
        t_str,                # setl_time  ← 每隔4秒
        psn_no,               # feelist_psn_no
        t_str,                # fee_ocur_time
        f"520300YZ{i+1:08d}\t",   # mdtrt_id
        INST_CODE_1,          # fixmedins_code
        INSTITUTION_1,        # fixmedins_name
        ITEM_CODE_1,          # hilist_code
        ITEM_NAME_1,          # hilist_name
        1.0,                  # cnt
        14.0,                 # pric
        14.0,                 # det_item_fee_sumamt
        "3",                  # fx_level
    ))

# 场景2：威宁县哲觉镇卫生院 10人×5秒 批量刷单
BASE_TIME_2 = datetime(2024, 4, 20, 23, 15, 0)
INSTITUTION_2 = "威宁县哲觉镇卫生院\t"
ITEM_NAME_2 = "布洛芬缓释胶囊\t"
ITEM_CODE_2 = "ZD01BAY0318010380001\t"
INST_CODE_2 = "H52052401001\t"

rows_2 = []
for i in range(10):
    t = BASE_TIME_2 + timedelta(seconds=i*5)
    t_str = t.strftime("%Y-%m-%d %H:%M:%S") + "\t"
    setl_id = f"QA26MOCK0002{i:04d}\t"
    psn_no = f"5200000200000000400{i+1:07d}\t"
    rows_2.append((
        "贵州省\t",
        "毕节市\t",
        "威宁县\t",
        psn_no,
        f"居民{i+1:03d}\t",
        f"52052319850{i+1:02d}151{i:03d}\t",
        psn_no,
        f"威宁哲觉村医王某\t",
        "15\t",
        "1\t",
        "1\t",
        42 + i,
        "390\t",
        "11\t",
        "15\t",
        "520500\t",
        setl_id,
        "2024-04-20 00:00:00\t",
        "2024-04-20 00:00:00\t",
        t_str,
        psn_no,
        t_str,
        f"520500WN{i+1:08d}\t",
        INST_CODE_2,
        INSTITUTION_2,
        ITEM_CODE_2,
        ITEM_NAME_2,
        1.0,
        12.0,
        12.0,
        "3",
    ))

all_rows = rows_1 + rows_2
col_names = [
    "prv_name", "city_name", "admdvs_name", "psn_no", "psn_name", "certno",
    "emp_no", "emp_name", "emp_type", "gend", "cert_gend", "age", "insutype",
    "med_type", "psn_type", "insu_admdvs", "setl_id", "begndate", "enddate",
    "setl_time", "feelist_psn_no", "fee_ocur_time", "mdtrt_id",
    "fixmedins_code", "fixmedins_name", "hilist_code", "hilist_name",
    "cnt", "pric", "det_item_fee_sumamt", "fx_level"
]

print(f"准备插入 {len(all_rows)} 条模拟批量刷单记录...")
print(f"  场景1: {INSTITUTION_1.strip()} × {len(rows_1)} 人 × 4秒间隔")
print(f"  场景2: {INSTITUTION_2.strip()} × {len(rows_2)} 人 × 5秒间隔")

try:
    client.insert("default.fqz_fymx_test", all_rows, column_names=col_names)
    print("✅ 插入成功！")
except Exception as e:
    print(f"❌ 插入失败: {e}")
    import traceback
    traceback.print_exc()

# 验证插入结果
print("\n=== 验证：查询刚插入的批量刷单记录 ===")
import clickhouse_connect
client2 = clickhouse_connect.get_client(host=host, port=port, database=db, username=user, password=pwd)

FIX_DT = "toDateTime(substring(trim(setl_time), 1, 19))"
sql = f"""
SELECT 
    toDate({FIX_DT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second', min({FIX_DT}), max({FIX_DT})) AS span_seconds,
    min({FIX_DT}) AS first_settle,
    max({FIX_DT}) AS last_settle
FROM default.fqz_fymx_test
WHERE fixmedins_name LIKE '%卫生%'
  AND (fixmedins_name LIKE '%庙塘%' OR fixmedins_name LIKE '%哲觉%')
GROUP BY setl_date, institution, item_name
ORDER BY patient_count DESC
"""
res = client2.query(sql)
print("列名:", res.column_names)
for r in res.result_rows:
    print(" ", r)

print("\n=== 全库时序批量刷单验证（>=5人/300秒内）===")
sql2 = f"""
SELECT 
    toDate({FIX_DT}) AS setl_date,
    trim(fixmedins_name) AS institution,
    trim(hilist_name) AS item_name,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second', min({FIX_DT}), max({FIX_DT})) AS span_seconds
FROM default.fqz_fymx_test
GROUP BY setl_date, institution, item_name
HAVING patient_count >= 5 AND span_seconds <= 300
ORDER BY patient_count DESC, span_seconds ASC
LIMIT 10
"""
res2 = client2.query(sql2)
print("列名:", res2.column_names)
for r in res2.result_rows:
    print(" ", r)
