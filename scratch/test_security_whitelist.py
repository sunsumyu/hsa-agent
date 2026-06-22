import os
import sys

# 强制设置 PYTHONPATH 以便导入 app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.infra.neo4j_manager import field_kg
from app.skills.schema_injector import BUILTIN_FIELD_SEEDS

def test_whitelist():
    # 模拟 SQLGuardian._validate_column_existence 的逻辑
    whitelist = {f["canonical"].lower() for f in field_kg.get_canonical_fields()}
    whitelist.update({f["field"].lower() for f in BUILTIN_FIELD_SEEDS})
    
    print(f"--- Whitelist Size: {len(whitelist)} ---")
    print(f"Is 'tel' in whitelist? {'tel' in whitelist}")
    print(f"Is 'gend' in whitelist? {'gend' in whitelist}")
    
    # 打印前 10 个字段确认
    print(f"First 10 fields: {list(whitelist)[:10]}")

if __name__ == "__main__":
    test_whitelist()
