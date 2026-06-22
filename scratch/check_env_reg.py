import winreg

def check_env_reg():
    print("--- Checking Registry Environment Variables ---")
    # User Environment
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            info = winreg.QueryInfoKey(key)
            for i in range(info[1]):
                name, val, _ = winreg.EnumValue(key, i)
                if 'codex' in name.lower() or 'codex' in val.lower():
                    print(f"USER ENV: {name} = {val}")
    except OSError as e:
        print(f"Error reading User Env Registry: {e}")

    # System Environment
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Control\Session Manager\Environment") as key:
            info = winreg.QueryInfoKey(key)
            for i in range(info[1]):
                name, val, _ = winreg.EnumValue(key, i)
                if 'codex' in name.lower() or 'codex' in val.lower():
                    print(f"SYSTEM ENV: {name} = {val}")
    except OSError as e:
        print(f"Error reading System Env Registry: {e}")

if __name__ == '__main__':
    check_env_reg()
