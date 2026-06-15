with open("scratch/run_7metrics_bench.py", "r", encoding="utf-8") as f:
    code = f.read()

import re
matches = re.findall(r'(\w+file\w*|\w*path\w*|\w*report\w*)\s*=\s*[\'"][^\'"]+[\'"]', code, re.IGNORECASE)
print("Potential file paths or output variables in run_7metrics_bench.py:")
for m in set(matches):
    print(f"  {m}")

# Find any writing to files in run_7metrics_bench.py
write_matches = [line.strip() for line in code.split('\n') if ".write(" in line or "open(" in line or "save" in line.lower()]
print("\nFile write or open calls in run_7metrics_bench.py:")
for w in write_matches[:30]:
    print(f"  {w}")
