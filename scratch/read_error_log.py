import sys

import sys

def read_log():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    # Read UTF-16LE error.log
    try:
        with open('error.log', 'r', encoding='utf-16le') as f:
            content = f.read()
        print("--- error.log tail (last 100 lines) ---")
        lines = content.split('\n')
        for line in lines[-100:]:
            print(line.strip())
            
        print("\n--- Searching for run_7metrics_bench in error.log ---")
        for i, line in enumerate(lines):
            if "run_7metrics" in line or "bench" in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 8)
                print(f"Match at line {i+1}:")
                for j in range(start, end):
                    print(f"  {j+1}: {lines[j].strip()}")
                print("-" * 50)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    read_log()

if __name__ == "__main__":
    read_log()
