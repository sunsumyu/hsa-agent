import sys

with open("logs/app_2026-06-14.log", "r", encoding="utf-8") as f:
    lines = f.readlines()

recent_lines = []
for i, line in enumerate(lines):
    # Match lines from 18:35 to 18:55
    if " 18:3" in line or " 18:4" in line or " 18:5" in line:
        recent_lines.append(f"Line {i+1}: {line.strip()}")

print(f"Total lines in log: {len(lines)}")
print(f"Found {len(recent_lines)} lines from 18:35 to 18:55")

with open("scratch/latest_case_runs.txt", "w", encoding="utf-8") as out_f:
    out_f.write("\n".join(recent_lines))
