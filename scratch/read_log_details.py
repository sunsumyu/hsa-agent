with open("logs/app_2026-06-14.log", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in log: {len(lines)}")
print("Last 10 lines of log:")
for line in lines[-10:]:
    print(f"  {line.strip()}")

matches = []
for i, line in enumerate(lines):
    if "QA-CUST-22" in line or "Malicious Patient Transfer" in line:
        matches.append((i+1, line.strip()))

print(f"Found {len(matches)} matches for QA-CUST-22:")
for line_num, content in matches[:20]:
    print(f"  Line {line_num}: {content}")
