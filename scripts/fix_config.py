import mysql.connector
import sys

def fix_config():
    # Try multiple common connection strings
    configs = [
        {"host": "172.18.27.30", "port": 15137, "user": "chuangzhi", "password": "test@123", "database": "its"},
        {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "root", "database": "its_nation"},
        {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "root", "database": "hsa_audit"}
    ]

    for config in configs:
        print(f"Trying connection to {config['host']}:{config['port']}...")
        try:
            conn = mysql.connector.connect(**config)
            print("Connection Success!")
            cursor = conn.cursor()
            
            # Insert or Update db_code=2 for ClickHouse
            sql = """
            INSERT INTO t_sys_ds_config (db_code, db_host, db_port, db_username, db_password, dbs_name, db_type)
            VALUES ('2', '127.0.0.1', '8123', 'default', '', 'default', 'CLICKHOUSE')
            ON DUPLICATE KEY UPDATE db_host='127.0.0.1', db_port='8123', db_type='CLICKHOUSE'
            """
            cursor.execute(sql)
            conn.commit()
            print("Successfully updated t_sys_ds_config for db_code='2'.")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"Failed: {e}")
    
    return False

if __name__ == "__main__":
    if fix_config():
        sys.exit(0)
    else:
        sys.exit(1)
