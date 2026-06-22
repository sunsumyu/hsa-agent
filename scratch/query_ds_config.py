import mysql.connector

config = {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "root", "database": "hsa_audit"}

try:
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM t_sys_ds_config")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
