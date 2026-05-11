"""
诊断脚本：检查 fqz_gz_jzsj_all_ql 中敏感字段的原始字节内容
目的：判断乱码是因为 GBK/UTF-8 编码问题，还是字段被加密
"""
import sys
sys.path.insert(0, 'e:/chain/hsa-agent-python')

from app.db_conn import get_clickhouse_client

client = get_clickhouse_client()

# 抽取 5 行，查看敏感字段的原始值
print("=" * 60)
print("[INFO] 抽样查看敏感字段原始内容")
print("=" * 60)

res = client.query("""
    SELECT 
        psn_no,
        psn_name,
        certno,
        tel,
        addr
    FROM fqz_gz_jzsj_all_ql
    LIMIT 5
""")

cols = res.column_names
for row in res.result_rows:
    print("\n--- Record ---")
    for i, col in enumerate(cols):
        val = row[i]
        val_str = str(val) if val is not None else "NULL"
        has_garbled = '\ufffd' in val_str or (len(val_str) > 0 and any(ord(c) > 127 and ord(c) < 0x4E00 for c in val_str))
        import re
        is_hash = bool(re.match(r'^[0-9a-fA-F]{16,}$', val_str.strip()))
        
        tag = ""
        if has_garbled: tag = " [WARNING: garbled]"
        elif is_hash: tag = " [ENCRYPTED: hash-like]"
        elif val_str == "NULL": tag = " [NULL]"
        
        print(f"  {col}: {val_str[:80]}{tag}")

print("\n" + "=" * 60)
print("[INFO] 检查 psn_name 的字节内容（判断编码）")
print("=" * 60)

res2 = client.query("SELECT psn_name FROM fqz_gz_jzsj_all_ql LIMIT 3")
for row in res2.result_rows:
    val = row[0]
    if isinstance(val, str):
        encoded = val.encode('utf-8', errors='replace')
        print(f"  raw value : {val[:50]}")
        print(f"  utf8 hex  : {encoded.hex()[:80]}")
        try:
            gbk_decoded = val.encode('latin-1').decode('gbk')
            print(f"  gbk decode: {gbk_decoded[:50]}")
        except Exception as ex:
            print(f"  gbk decode failed: {ex}")
    print()
