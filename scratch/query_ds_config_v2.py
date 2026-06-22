import mysql.connector

config = {"host": "127.0.0.1", "port": 3308, "user": "root", "password": "62901990552", "database": "fylqz_platform_new"}

try:
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    # Check for t_sys_ds_config or similar
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"Tables: {tables}")
    
    # Try to find config table
    config_table = None
    for t in tables:
        name = list(t.values())[0]
        if "config" in name.lower() or "ds" in name.lower():
            config_table = name
            print(f"Found potential config table: {config_table}")
            cursor.execute(f"SELECT * FROM {config_table}")
            rows = cursor.fetchall()
            for row in rows:
                print(row)
    
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
