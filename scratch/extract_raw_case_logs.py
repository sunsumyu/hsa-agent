import re

def main():
    log_file = "E:/chain/hsa-agent/logs/app_2026-06-14.log"
    # Extract logs between 15:41:00 and 15:49:00
    pattern = re.compile(r"^2026-06-14 15:(4[1-9])")
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    out = []
    for line in lines:
        if pattern.match(line):
            out.append(line.strip())
            
    print(f"Extracted {len(out)} lines.")
    with open("scratch/case_runs.log", "w", encoding="utf-8") as f:
        f.write("\n".join(out))

if __name__ == '__main__':
    main()
