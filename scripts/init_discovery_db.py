"""初始化 cloud_discovery SQLite 数据库，支持增量 UPSERT，防止数据覆盖"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cloud_discovery.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS models (
            name TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            remaining TEXT DEFAULT '0',
            total TEXT DEFAULT '0',
            status TEXT DEFAULT 'OK',
            hint TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def upsert_model(conn, name, platform, remaining, total, status='OK', hint=''):
    conn.execute("""
        INSERT INTO models (name, platform, remaining, total, status, hint, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET
            remaining=excluded.remaining,
            total=excluded.total,
            status=excluded.status,
            hint=excluded.hint,
            updated_at=CURRENT_TIMESTAMP
    """, (name, platform, remaining, total, status, hint))

def bulk_upsert(models):
    conn = init_db()
    for m in models:
        status = m.get('status', 'OK')
        # 自动计算状态
        try:
            rem = int(m['remaining'].replace(',', ''))
            tot = int(m['total'].replace(',', ''))
            if tot > 0 and rem / tot < 0.05:
                status = 'Critical'
            elif tot > 0 and rem / tot < 0.15:
                status = 'Warning'
            elif rem < tot:
                status = 'Active'
        except Exception:
            pass
        upsert_model(conn, m['name'], m['platform'], m['remaining'], m['total'], status, m.get('hint', ''))
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
    conn.close()
    print(f"[OK] SQLite DB updated: {count} models in {DB_PATH}")
    return count

if __name__ == "__main__":
    # 从现有 JSON 迁移
    import json
    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "cloud_discovery.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        bulk_upsert(data)
    else:
        init_db()
        print("DB initialized (empty)")
