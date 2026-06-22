"""验证 _clean_encrypted_fields 是否正确清洗了加密数据"""
import sys, os
sys.path.insert(0, '.')
os.environ['LOGURU_LEVEL'] = 'ERROR'

from app.tools import _execute_audit_sql_logic

# 查询包含加密字段的数据
print("=== 清洗前后对比 (10 rows, offset 100) ===\n")
result = _execute_audit_sql_logic(
    "SELECT psn_name, certno, fixmedins_code, fixmedins_name, gend, medfee_sumamt, admdvs_cityname FROM fqz_gz_jzsj_all_ql WHERE psn_name != '' LIMIT 10 OFFSET 100",
    return_raw=True
)

if isinstance(result, str):
    print(f"查询失败: {result}")
else:
    encrypted_fields = ['psn_name', 'certno', 'fixmedins_code', 'fixmedins_name']
    normal_fields = ['gend', 'medfee_sumamt', 'admdvs_cityname']
    
    clean_count = 0
    dirty_count = 0
    
    for i, row in enumerate(result):
        print(f"Row {i+1}:")
        for field in encrypted_fields:
            val = str(row.get(field, 'N/A'))
            status = "CLEANED(空)" if val == '' else f"未清洗! val={val[:40]}"
            if val == '':
                clean_count += 1
            else:
                dirty_count += 1
            print(f"  [加密] {field:20s} -> {status}")
        
        for field in normal_fields:
            val = str(row.get(field, 'N/A'))
            has_bad = '\ufffd' in val or any(ord(c) < 32 and c not in '\n\r\t' for c in val)
            status = f"{val}" + (" *** 被误清洗!" if val == '' and field in ['gend', 'medfee_sumamt'] else "")
            print(f"  [正常] {field:20s} -> {status}")
        print()
    
    print(f"=== 结论 ===")
    print(f"  加密字段清洗成功: {clean_count} 个")
    print(f"  加密字段未清洗:   {dirty_count} 个")
    print(f"  结果: {'✅ 全部通过' if dirty_count == 0 else '❌ 存在遗漏'}")
