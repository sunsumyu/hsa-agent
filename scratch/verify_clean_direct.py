"""直接连 ClickHouse 验证加密清洗逻辑（绕过 app 模块依赖）"""
import clickhouse_connect

c = clickhouse_connect.get_client(host='localhost', port=8123)

# 获取原始数据（未清洗）
r = c.query("""
    SELECT psn_name, certno, fixmedins_code, fixmedins_name, gend, medfee_sumamt, admdvs_cityname 
    FROM fqz_gz_jzsj_all_ql 
    WHERE psn_name != '' 
    LIMIT 5 OFFSET 100
""")

cols = r.column_names
enc_fields = {'psn_name', 'certno', 'fixmedins_code', 'fixmedins_name'}

print("=== 原始数据（未清洗） ===")
for i, row in enumerate(r.result_rows):
    print(f"Row {i+1}:")
    for j in range(len(cols)):
        val = str(row[j])
        is_enc = cols[j] in enc_fields
        has_bad = '\ufffd' in val or any(ord(c) < 32 and c not in '\n\r\t' for c in val)
        print(f"  [{('ENC' if is_enc else 'OK ')}] {cols[j]:20s} = {val[:50]:50s} {'*** DIRTY' if has_bad else 'CLEAN'}")
    print()

# 模拟清洗逻辑
print("=== 清洗后 ===")
records = [{cols[j]: row[j] for j in range(len(cols))} for row in r.result_rows]

for row in records:
    for key, val in row.items():
        if not isinstance(val, str) or len(val) < 2:
            continue
        has_replacement = '\ufffd' in val
        has_binary = any(ord(c) < 32 and c not in '\n\r\t' for c in val)
        if has_replacement or has_binary:
            row[key] = ""

for i, row in enumerate(records):
    print(f"Row {i+1}:")
    for col in cols:
        val = str(row[col])
        is_enc = col in enc_fields
        if is_enc:
            status = "CLEANED" if val == "" else f"LEAK! val={val[:30]}"
        else:
            status = f"{val[:50]}" + (" *** FALSE POSITIVE!" if val == "" and col in ['gend', 'admdvs_cityname'] else "")
        print(f"  [{('ENC' if is_enc else 'OK ')}] {col:20s} -> {status}")
    print()

# 统计
enc_total = 0
enc_cleaned = 0
normal_damaged = 0
for row in records:
    for col in cols:
        val = str(row[col])
        if col in enc_fields:
            enc_total += 1
            if val == "":
                enc_cleaned += 1
        else:
            if val == "" and col in ['gend', 'medfee_sumamt', 'admdvs_cityname']:
                normal_damaged += 1

print(f"=== 验证结论 ===")
print(f"  加密字段: {enc_cleaned}/{enc_total} 已清洗")
print(f"  正常字段误清洗: {normal_damaged}")
print(f"  结果: {'PASS' if enc_cleaned == enc_total and normal_damaged == 0 else 'FAIL'}")
