import sqlite3
import os
import time
import sys

def query_db():
    db_path = r"C:\Users\AREN\.codex\logs_2.sqlite"
    if not os.path.exists(db_path):
        print("Database not found")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Keywords to search in logs
    keywords = ['window', 'fullscreen', 'bounds', 'display', 'screen', 'gpu', 'maximized', 'maximize', 'crash', 'fail', 'error', 'trans', 'transparent', 'theme']
    
    print("--- Searching for logs containing UI/Window keywords ---")
    
    # Filter out verbose library targets
    query = """
    SELECT ts, level, target, feedback_log_body, file, line 
    FROM logs 
    WHERE (level IN ('ERROR', 'WARN', 'WARNING') 
           OR ({kw_cond}))
      AND target NOT LIKE 'opentelemetry%'
      AND target NOT LIKE 'hyper%'
      AND target NOT LIKE 'h2%'
      AND target NOT LIKE 'rustls%'
      AND target NOT LIKE 'tokio%'
      AND target NOT LIKE 'reqwest%'
    ORDER BY ts DESC, ts_nanos DESC 
    LIMIT 500
    """.format(kw_cond=" OR ".join([f"feedback_log_body LIKE '%{kw}%'" for kw in keywords]))
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    out_path = r"e:\chain\hsa-agent\scratch\searched_logs.txt"
    print(f"Found {len(rows)} matching logs. Writing to {out_path}")
    
    with open(out_path, 'w', encoding='utf-8') as f:
        for r in rows:
            ts, level, target, body, filename, line = r
            t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
            log_line = f"[{t_str}] [{level}] [{target}] at {filename}:{line}\n  Body: {body}\n\n"
            f.write(log_line)
            
    print("Write complete.")

if __name__ == "__main__":
    # Ensure stdout handles utf-8 if we print
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    query_db()

