import os
import clickhouse_connect
from dotenv import load_dotenv

def update_admdvs():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    # 物理 DDL 序列
    commands = [
        "ALTER TABLE fqz_admdvs MODIFY COMMENT '行政区划维表 - 全国医保标准代码对照'",
        "ALTER TABLE fqz_admdvs COMMENT COLUMN admdvs '行政区划代码'",
        "ALTER TABLE fqz_admdvs COMMENT COLUMN admdvs_name '行政区划名称'",
        "ALTER TABLE fqz_admdvs COMMENT COLUMN prnt_admdvs '父级区划代码 (100000代表国家级)'",
        "ALTER TABLE fqz_admdvs COMMENT COLUMN admdvs_lv '区划级别 (0:国家/1:省/2:市)'"
    ]
    
    print(">>> 正在为 fqz_admdvs 注入物理语义...")
    for cmd in commands:
        try:
            client.command(cmd)
            print(f"SUCCESS: {cmd[:40]}...")
        except Exception as e:
            print(f"FAILED: {cmd[:40]}... ERROR: {e}")
    
    client.close()
    print("\n>>> fqz_admdvs 元数据加固完成。")

if __name__ == "__main__":
    update_admdvs()
