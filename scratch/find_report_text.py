with open("scratch/run_7metrics_bench.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "report_text" in line or "report" in line.lower():
        if "reporter" not in line and "report_renderer" not in line:
            print(f"Line {i+1}: {line.strip()}")
