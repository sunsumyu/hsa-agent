import os

def find_logs():
    possible_paths = [
        r"C:\Users\AREN\.codex",
        r"C:\Users\AREN\AppData\Local\OpenAI",
        r"C:\Users\AREN\AppData\Roaming\OpenAI",
        r"C:\Users\AREN\AppData\Roaming\Codex",
    ]
    for path in possible_paths:
        if not os.path.exists(path):
            print(f"Path does not exist: {path}")
            continue
        print(f"Scanning: {path}")
        for root, dirs, files in os.walk(path):
            for file in files:
                if any(ext in file.lower() for ext in ['.log', '.txt', 'err', 'out', 'info', '.jsonl']):
                    full_path = os.path.join(root, file)
                    try:
                        sz = os.path.getsize(full_path)
                        if sz > 0:
                            print(f"  {full_path} ({sz} bytes)")
                    except Exception:
                        pass

if __name__ == "__main__":
    find_logs()
