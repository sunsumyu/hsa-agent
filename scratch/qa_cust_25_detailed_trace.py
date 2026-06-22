import re

log_path = r"e:\chain\hsa-agent\logs\app_2026-06-05.log"
output_path = r"e:\chain\hsa-agent\scratch\qa_cust_25_detailed_trace.txt"

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Let's find all occurrences of QA-CUST-25 and print the surrounding lines (e.g. 500 lines before and after)
matches = [m.start() for m in re.finditer("QA-CUST-25", content)]
print(f"Found {len(matches)} matches for QA-CUST-25")

extracted = []
for idx, m in enumerate(matches):
    start = max(0, m - 5000)
    end = min(len(content), m + 25000)
    extracted.append(f"--- MATCH {idx+1} ---")
    extracted.append(content[start:end])

with open(output_path, 'w', encoding='utf-8') as out_f:
    out_f.write("\n\n".join(extracted))

print(f"Detailed trace written to {output_path}")
