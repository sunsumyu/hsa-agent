import sys

# Ensure UTF-8 output if printing, but we will write to file
with open("logs/app_2026-06-14.log", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total log lines: {len(lines)}")

cust_22_lines = []
for i, line in enumerate(lines):
    # Check for CUST-22 or CUST-23 or CUST-24 or timestamps in 16:
    if "QA-CUST-22" in line or "16:" in line or "Malicious Patient" in line:
        cust_22_lines.append(f"Line {i+1}: {line.strip()}")

print(f"Found {len(cust_22_lines)} matching lines.")
with open("scratch/cust_22_logs.txt", "w", encoding="utf-8") as out_f:
    out_f.write("\n".join(cust_22_lines))

# Also write the last 50 lines of the log to another file to see where it ends
with open("scratch/last_log_lines.txt", "w", encoding="utf-8") as last_f:
    last_f.write("\n".join(line.strip() for line in lines[-50:]))
