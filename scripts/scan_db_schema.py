import os
import json
import clickhouse_connect
import mysql.connector
from datetime import datetime

# ClickHouse 配置
CK_CONFIG = {
    "host": "127.0.0.1",
    "port": 8123,
    "database": "default"
}

# MySQL 配置
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3308,
    "user": "root",
    "password": "62901990552",
    "database": "fylqz_platform_new"
}

OUTPUT_DIR = r"C:\Users\AREN\.gemini\antigravity\knowledge"

def scan_clickhouse():
    print(">>> 正在扫描 ClickHouse...")
    client = clickhouse_connect.get_client(**CK_CONFIG)
    
    # 获取表列表
    tables = client.query("SHOW TABLES").result_rows
    schema_data = {}
    
    for (table_name,) in tables:
        print(f"  扫描表: {table_name}")
        # 获取列信息：名称、类型、注释
        cols = client.query(f"SELECT name, type, comment FROM system.columns WHERE table = '{table_name}' AND database = '{CK_CONFIG['database']}'").result_rows
        
        # 获取样例数据 (脱敏)
        try:
            samples = client.query(f"SELECT * FROM {table_name} LIMIT 3").result_rows
            col_names = client.query(f"SELECT name FROM system.columns WHERE table = '{table_name}' AND database = '{CK_CONFIG['database']}'").result_rows
            sample_list = []
            for row in samples:
                sample_list.append({name[0]: str(val) for name, val in zip(col_names, row)})
        except Exception as e:
            sample_list = [f"无法获取数据: {str(e)}"]

        schema_data[table_name] = {
            "columns": [{"name": c[0], "type": c[1], "comment": c[2]} for c in cols],
            "samples": sample_list
        }
    
    return schema_data

def scan_mysql():
    print(">>> 正在扫描 MySQL...")
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(dictionary=True)
    
    # 获取所有表
    cursor.execute("SHOW TABLES")
    tables = [list(row.values())[0] for row in cursor.fetchall()]
    schema_data = {}
    
    for table_name in tables:
        print(f"  扫描表: {table_name}")
        # 获取详细列信息 (包含 Comment)
        cursor.execute(f"SHOW FULL COLUMNS FROM {table_name}")
        cols = cursor.fetchall()
        
        # 获取样例数据
        try:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
            samples = cursor.fetchall()
            # 转为字符串避免 JSON 错误
            sample_list = [{k: str(v) for k, v in row.items()} for row in samples]
        except Exception as e:
            sample_list = [f"无法获取数据: {str(e)}"]

        schema_data[table_name] = {
            "columns": [{"name": c['Field'], "type": c['Type'], "comment": c['Comment']} for c in cols],
            "samples": sample_list
        }
    
    conn.close()
    return schema_data

def write_md(name, data, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {name} 数据库结构详表\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for table, detail in data.items():
            f.write(f"## 表: `{table}`\n\n")
            f.write("### 字段定义\n\n")
            f.write("| 字段名 | 类型 | 注释 |\n")
            f.write("| :--- | :--- | :--- |\n")
            for col in detail["columns"]:
                f.write(f"| {col['name']} | {col['type']} | {col['comment']} |\n")
            f.write("\n")
            
            f.write("### 数据样例 (前3条)\n\n")
            if detail["samples"] and isinstance(detail["samples"][0], dict):
                f.write("```json\n")
                f.write(json.dumps(detail["samples"], indent=2, ensure_ascii=False))
                f.write("\n```\n\n")
            else:
                f.write(f"{detail['samples']}\n\n")
            f.write("---\n\n")
    print(f">>> 已写入: {filepath}")

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    ck_data = scan_clickhouse()
    write_md("ClickHouse", ck_data, "db_schema_clickhouse.md")
    
    ms_data = scan_mysql()
    write_md("MySQL (fylqz_platform_new)", ms_data, "db_schema_mysql.md")
    
    print(">>> 扫描任务完成！")
