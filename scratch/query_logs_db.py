import sqlite3
import os

def query_db():
    db_path = r"C:\Users\AREN\.codex\logs_2.sqlite"
    if not os.path.exists(db_path):
        print("Database not found")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    # Let's inspect each table schema
    for table in tables:
        tname = table[0]
        cursor.execute(f"PRAGMA table_info({tname});")
        print(f"\nTable {tname} schema:")
        for col in cursor.fetchall():
            print(f"  {col[1]} ({col[2]})")
            
        # Get count
        cursor.execute(f"SELECT count() FROM {tname};")
        count = cursor.fetchone()[0]
        print(f"  Total rows: {count}")
        
        # Get last 5 rows if there are any
        if count > 0:
            print(f"  Last 5 rows in {tname}:")
            cursor.execute(f"SELECT * FROM {tname} ORDER BY rowid DESC LIMIT 5;")
            rows = cursor.fetchall()
            for r in rows:
                print(f"    {str(r)[:300]}...")

if __name__ == "__main__":
    query_db()
