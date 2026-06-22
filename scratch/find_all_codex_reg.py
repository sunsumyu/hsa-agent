import winreg

def search_keys(root, root_name, path):
    found = []
    try:
        with winreg.OpenKey(root, path) as key:
            info = winreg.QueryInfoKey(key)
            for i in range(info[0]): # subkeys
                try:
                    name = winreg.EnumKey(key, i)
                    full_path = f"{path}\\{name}" if path else name
                    if 'codex' in name.lower():
                        found.append(f"{root_name}\\{full_path}")
                    # Recurse a bit, but limit depth to avoid infinite loop
                    if full_path.count('\\') < 3:
                        found.extend(search_keys(root, root_name, full_path))
                except OSError:
                    continue
    except OSError:
        pass
    return found

def main():
    print("--- Searching Registry for 'Codex' Keys ---")
    keys = []
    keys.extend(search_keys(winreg.HKEY_CURRENT_USER, "HKCU", "Software"))
    keys.extend(search_keys(winreg.HKEY_LOCAL_MACHINE, "HKLM", "Software"))
    for k in keys:
        print(f"FOUND KEY: {k}")

if __name__ == '__main__':
    main()
