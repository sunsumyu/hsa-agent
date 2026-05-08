"""
[V57.3] 编码诊断脚本：分析 ClickHouse 返回数据中的编码问题
目标：区分 (1) 终端显示问题 (2) 真实编码损坏 (3) 加密数据
"""
import sys, os
sys.path.insert(0, '.')
os.environ['LOGURU_LEVEL'] = 'ERROR'

from app.tools import get_clickhouse_client

client = get_clickhouse_client()

# =============================================
# STEP 1: 表结构（真实物理字段）
# =============================================
print("=" * 70)
print("  STEP 1: 物理表真实字段 (DESCRIBE TABLE)")
print("=" * 70)
desc = client.query("DESCRIBE TABLE fqz_gz_jzsj_all_ql")
for row in desc.result_rows:
    print(f"  {row[0]:30s} | {row[1]}")

# =============================================
# STEP 2: 取 5 条原始数据逐字段检查
# =============================================
print("\n" + "=" * 70)
print("  STEP 2: 原始数据样本 (5 rows)")
print("=" * 70)
sample = client.query("SELECT * FROM fqz_gz_jzsj_all_ql LIMIT 5")

# 获取列名
col_names = sample.column_names if hasattr(sample, "column_names") else [f"col_{i}" for i in range(50)]
print(f"  Total columns: {len(col_names)}")
print(f"  Column names: {col_names}")

for i, row in enumerate(sample.result_rows):
    print(f"\n  --- Row {i+1} ---")
    for j, val in enumerate(row):
        col = col_names[j] if j < len(col_names) else f"col_{j}"
        val_str = str(val)
        
        # 检测标志
        flags = []
        
        # 1. Unicode 替换字符 (编码损坏)
        if "\ufffd" in val_str:
            flags.append("REPLACEMENT_CHAR(\ufffd)")
        
        # 2. 不可打印控制字符
        ctrl_count = sum(1 for c in val_str if ord(c) < 32 and c not in "\n\r\t")
        if ctrl_count > 0:
            flags.append(f"CONTROL_CHARS({ctrl_count})")
        
        # 3. 高比例非ASCII字符 (可能是加密数据)
        if len(val_str) > 20:
            non_ascii_ratio = sum(1 for c in val_str if ord(c) > 127) / len(val_str)
            if non_ascii_ratio > 0.5:
                flags.append(f"HIGH_ENTROPY({non_ascii_ratio:.0%})")
        
        # 4. 包含常见乱码特征
        garble_chars = sum(1 for c in val_str if c in "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f")
        if garble_chars > 0:
            flags.append(f"BINARY_GARBAGE({garble_chars})")
        
        flag_str = f"  *** [{' | '.join(flags)}]" if flags else ""
        
        # 截断显示
        display = val_str[:80] + ("..." if len(val_str) > 80 else "")
        print(f"  {col:25s} = {display}{flag_str}")

# =============================================
# STEP 3: 专门检查中文字段的编码质量
# =============================================
print("\n" + "=" * 70)
print("  STEP 3: 中文字段编码质量检查")
print("=" * 70)

# 查询包含中文的典型字段
try:
    zh_sample = client.query("""
        SELECT psn_no, gend, med_list_name, diag_name, fixmedins_name, setl_time
        FROM fqz_gz_jzsj_all_ql 
        LIMIT 10
    """)
    zh_cols = zh_sample.column_names if hasattr(zh_sample, "column_names") else []
    print(f"  查询字段: {zh_cols}")
    
    for i, row in enumerate(zh_sample.result_rows):
        print(f"\n  Row {i+1}:")
        for j, val in enumerate(row):
            col = zh_cols[j] if j < len(zh_cols) else f"col_{j}"
            val_str = str(val)
            
            # 对中文字段进行编码往返测试
            try:
                encoded = val_str.encode("utf-8")
                decoded = encoded.decode("utf-8")
                roundtrip_ok = (decoded == val_str)
            except:
                roundtrip_ok = False
            
            status = "OK" if roundtrip_ok and "\ufffd" not in val_str else "DAMAGED"
            print(f"    {col:20s} = {val_str[:60]:60s}  [{status}]")
except Exception as e:
    print(f"  查询失败: {e}")
    print("  这可能意味着某些字段名不存在，需要根据 STEP 1 的结果修正")

print("\n" + "=" * 70)
print("  诊断完成")
print("=" * 70)
