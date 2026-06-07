import re

log_path = r"e:\chain\hsa-agent\logs\app_2026-06-05.log"
with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Let's search for "BENCH_QA" or "QA-CUST" or "CUST"
matches = re.findall(r"BENCH_QA-CUST-\d+|QA-CUST-\d+", content)
print(f"Total matches found: {len(matches)}")
print(f"Unique matches: {set(matches)}")
