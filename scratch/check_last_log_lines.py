import sys

path = r"e:\chain\hsa-agent\logs\app_2026-06-05.log"
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lines in log: {len(lines)}")
print("--- Last 15 lines of log ---")
for line in lines[-15:]:
    safe_line = line.encode('gbk', errors='replace').decode('gbk')
    print(safe_line.strip())
