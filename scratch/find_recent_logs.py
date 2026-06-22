import os
import time

def find_recent_logs():
    paths = [
        r"C:\Users\AREN\.codex",
        r"C:\Users\AREN\AppData\Local\OpenAI",
        r"C:\Users\AREN\AppData\Roaming\Codex",
    ]
    now = time.time()
    two_days_ago = now - 2 * 24 * 3600
    
    print("--- Files modified in the last 2 days ---")
    for path in paths:
        if not os.path.exists(path):
            continue
        for root, dirs, files in os.walk(path):
            for file in files:
                full_path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(full_path)
                    if mtime > two_days_ago:
                        sz = os.path.getsize(full_path)
                        t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                        print(f"[{t_str}] {full_path} ({sz} bytes)")
                except Exception:
                    pass

if __name__ == "__main__":
    find_recent_logs()
