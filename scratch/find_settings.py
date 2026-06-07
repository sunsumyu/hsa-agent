import os

roaming = os.path.expandvars(r'%APPDATA%')
print("--- Searching settings.json for 'codex' ---")
for root, dirs, files in os.walk(roaming):
    depth = root[len(roaming):].count(os.sep)
    if depth > 4:
        dirs.clear()
        continue
    if 'settings.json' in files:
        path = os.path.join(root, 'settings.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            found_lines = []
            for idx, line in enumerate(lines):
                if 'codex' in line.lower():
                    found_lines.append((idx + 1, line.strip()))
            if found_lines:
                print(f"Found in {path}:")
                for num, content in found_lines:
                    print(f"  Line {num}: {content}")
        except Exception as e:
            print(f"Error reading {path}: {e}")
