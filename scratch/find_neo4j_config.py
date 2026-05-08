import mysql.connector

config = {"host": "127.0.0.1", "port": 3308, "user": "root", "password": "62901990552", "database": "fylqz_platform_new"}

try:
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM t_sys_ds_config WHERE db_type = 'NEO4J'")
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"NEO4J_CONFIG: {row}")
    else:
        print("No NEO4J config in t_sys_ds_config")
        cursor.execute("SELECT * FROM t_sys_ds_config")
        for row in cursor.fetchall():
            print(row)
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
