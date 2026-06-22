import os

def parse_log():
    log_path = r"C:\Users\AREN\.gemini\antigravity-ide\brain\7ac1af47-d59e-4da7-b5e8-6f1fc0308504\.system_generated\tasks\task-655.log"
    if not os.path.exists(log_path):
        print("Log not found")
        return
        
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    print(f"Total lines in log: {len(lines)}")
    
    # Ensure stdout is UTF-8
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    # Print the last 50 lines first
    print("\n--- Last 50 lines ---")
    for line in lines[-50:]:
        print(line.strip().encode('utf-8', errors='ignore').decode('utf-8'))
        
    # Search for exceptions
    print("\n--- Searching for Exception/Traceback ---")
    for i, line in enumerate(lines):
        if "traceback" in line.lower() or "exception" in line.lower() or "error" in line.lower() or "failed" in line.lower():
            # print surrounding lines
            start = max(0, i - 2)
            end = min(len(lines), i + 5)
            print(f"\nMatch at line {i+1}:")
            for j in range(start, end):
                print(f"  {j+1}: {lines[j].strip().encode('utf-8', errors='ignore').decode('utf-8')}")
            print("-" * 50)

if __name__ == "__main__":
    parse_log()
