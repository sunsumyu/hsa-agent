import sys, os
sys.path.insert(0, '.')
os.environ['LOGURU_LEVEL'] = 'ERROR'

from app.tools import get_clickhouse_client
client = get_clickhouse_client()

print("=== psn_name / certno (non-empty samples, offset 100) ===")
r = client.query("""
    SELECT psn_name, certno, fixmedins_code, fixmedins_name, addr
    FROM fqz_gz_jzsj_all_ql 
    WHERE psn_name != '' AND certno != '' 
    LIMIT 10 OFFSET 100
""")
cols = ['psn_name', 'certno', 'fixmedins_code', 'fixmedins_name', 'addr']
for i, row in enumerate(r.result_rows):
    print(f"Row {i+1}:")
    for j, col in enumerate(cols):
        val = str(row[j])
        has_replacement = '\ufffd' in val
        has_binary = any(ord(c) < 32 and c not in '\n\r\t' for c in val)
        # 高比例非标准字符
        if len(val) > 5:
            weird_ratio = sum(1 for c in val if ord(c) > 127 and not ('\u4e00' <= c <= '\u9fff')) / len(val)
        else:
            weird_ratio = 0
        
        tags = []
        if has_replacement: tags.append("REPLACEMENT")
        if has_binary: tags.append("BINARY")
        if weird_ratio > 0.3: tags.append(f"NON_CJK_HIGH({weird_ratio:.0%})")
        
        tag = f"  *** [{', '.join(tags)}]" if tags else ""
        print(f"  {col:20s} = {val[:70]}{tag}")
    print()

print("=== ALL encrypted field candidates (distinct check) ===")
# 统计有多少条 psn_name 包含乱码
r2 = client.query("""
    SELECT 
        count(*) as total,
        countIf(psn_name = '') as name_empty,
        countIf(certno = '') as cert_empty,
        countIf(fixmedins_code = '') as code_empty
    FROM fqz_gz_jzsj_all_ql
""")
for row in r2.result_rows:
    print(f"  Total rows: {row[0]}")
    print(f"  psn_name empty: {row[1]} ({row[1]/row[0]*100:.1f}%)")
    print(f"  certno empty:   {row[2]} ({row[2]/row[0]*100:.1f}%)")
    print(f"  fixmedins_code empty: {row[3]} ({row[3]/row[0]*100:.1f}%)")
