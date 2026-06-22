import os
from datetime import datetime

def main():
    workspace = "E:/chain/hsa-agent"
    start_time = datetime(2026, 6, 14, 16, 50, 0)
    end_time = datetime(2026, 6, 14, 17, 10, 0)
    
    recent_files = []
    for root, dirs, files in os.walk(workspace):
        # Skip pycache and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for file in files:
            path = os.path.join(root, file)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
                if start_time <= mtime <= end_time:
                    recent_files.append((path, mtime))
            except Exception:
                pass
                
    recent_files.sort(key=lambda x: x[1])
    print(f"Found {len(recent_files)} files modified between 16:50 and 17:10:")
    for path, mtime in recent_files:
        print(f"  {path} (Modified: {mtime})")

if __name__ == '__main__':
    main()
