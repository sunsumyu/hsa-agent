import psutil
import os

print("--- Listing processes ---")
for p in psutil.process_iter(['pid', 'name', 'exe']):
    try:
        exe = p.info['exe'] or ''
        name = p.info['name'] or ''
        if 'antigravity' in exe.lower() or 'code' in name.lower() or 'codex' in name.lower():
            print(f"PID {p.info['pid']}: {name} ({exe})")
    except Exception as e:
        pass
