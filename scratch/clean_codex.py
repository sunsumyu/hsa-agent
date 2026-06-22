import os
import sys
import json
import shutil
import stat
import psutil
import winreg
import ctypes
from ctypes import wintypes

def kill_processes():
    print("1. Terminating Codex processes...")
    killed = 0
    for p in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            exe = p.info['exe'] or ''
            name = p.info['name'] or ''
            if 'codex' in name.lower() or 'codex' in exe.lower():
                print(f"  Killing process PID {p.info['pid']}: {name} ({exe})")
                p.kill()
                killed += 1
        except Exception as e:
            print(f"  Failed to kill PID {p.info['pid']}: {e}")
    print(f"  Terminated {killed} process(es).")

def remove_readonly(func, path, excinfo):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        print(f"    Failed to remove readonly attribute and delete {path}: {e}")

def delete_directory(path):
    if os.path.exists(path):
        print(f"  Deleting: {path}")
        try:
            shutil.rmtree(path, onerror=remove_readonly)
            # double check if it is gone
            if not os.path.exists(path):
                print("    Successfully deleted.")
            else:
                print("    Failed to delete some files (directory still exists).")
        except Exception as e:
            print(f"    Error deleting {path}: {e}")
    else:
        print(f"  Folder not found: {path} (already clean)")

def delete_local_folders():
    print("2. Deleting local directories...")
    paths = [
        os.path.expandvars(r'%USERPROFILE%\.codex'),
        os.path.expandvars(r'%APPDATA%\Codex'),
        os.path.expandvars(r'%LOCALAPPDATA%\Codex'),
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Codex'),
        r'C:\Program Files\Codex',
        r'C:\Program Files (x86)\Codex',
        os.path.expandvars(r'%USERPROFILE%\.antigravity-ide\extensions\openai.chatgpt-26.601.20914-win32-x64')
    ]
    for p in paths:
        delete_directory(p)

def update_extensions_json():
    print("3. Updating IDE extensions.json...")
    ext_json_path = os.path.expandvars(r'%USERPROFILE%\.antigravity-ide\extensions\extensions.json')
    if os.path.exists(ext_json_path):
        try:
            with open(ext_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Find and remove openai.chatgpt
            new_data = []
            removed = False
            for ext in data:
                ext_id = ext.get('identifier', {}).get('id', '')
                if ext_id == 'openai.chatgpt':
                    print(f"  Removing extension metadata: {ext_id} v{ext.get('version')}")
                    removed = True
                else:
                    new_data.append(ext)
            
            if removed:
                with open(ext_json_path, 'w', encoding='utf-8') as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=None)
                print("  extensions.json updated successfully.")
            else:
                print("  openai.chatgpt not found in extensions.json (already clean).")
        except Exception as e:
            print(f"  Error updating extensions.json: {e}")
    else:
        print("  extensions.json not found.")

def delete_reg_value(root, path, value_name):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value_name)
            print(f"  Deleted Registry Value: {value_name} in {path}")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  Error deleting registry value {value_name} from {path}: {e}")

def delete_reg_key_recursive(root, root_name, path):
    try:
        # First try to open with write permission
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
            # We must enumerate and delete subkeys first
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, 0)
                    delete_reg_key_recursive(root, root_name, f"{path}\\{subkey_name}")
                except OSError:
                    # No more subkeys
                    break
        # Now delete the key itself
        winreg.DeleteKey(root, path)
        print(f"  Deleted Registry Key: {root_name}\\{path}")
    except FileNotFoundError:
        pass
    except Exception as e:
        # Avoid printing permission denied errors for HKLM keys as they are expected
        if root_name == "HKLM" and "Access is denied" in str(e):
            pass
        else:
            print(f"  Error deleting registry key {root_name}\\{path}: {e}")

def clean_registry():
    print("4. Cleaning Registry and environment variables...")
    
    # User Environment Variables
    delete_reg_value(winreg.HKEY_CURRENT_USER, "Environment", "CODEX_API_KEY")
    # Check if OPENAI_BASE_URL contains codex before deleting
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "OPENAI_BASE_URL")
            if 'codex' in val.lower():
                delete_reg_value(winreg.HKEY_CURRENT_USER, "Environment", "OPENAI_BASE_URL")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"  Error checking/deleting OPENAI_BASE_URL env var: {e}")

    # Software Keys
    delete_reg_key_recursive(winreg.HKEY_CURRENT_USER, "HKCU", r"Software\Chromium\PreferenceMACs\codex-browser-app")
    delete_reg_key_recursive(winreg.HKEY_CURRENT_USER, "HKCU", r"Software\Classes\codex")
    
    # Tracing Keys (HKLM)
    delete_reg_key_recursive(winreg.HKEY_LOCAL_MACHINE, "HKLM", r"Software\Microsoft\Tracing\Codex Installer_RASAPI32")
    delete_reg_key_recursive(winreg.HKEY_LOCAL_MACHINE, "HKLM", r"Software\Microsoft\Tracing\Codex Installer_RASMANCS")

def broadcast_env_change():
    print("5. Broadcasting environment change signal...")
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        
        # SendMessageTimeoutW
        result = ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            'Environment',
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(wintypes.DWORD())
        )
        print("  Broadcast completed successfully. Active applications have been notified.")
    except Exception as e:
        print(f"  Failed to broadcast environment change: {e}")

def main():
    print("=== Codex Residue Cleanup (Fix Read-only) Started ===")
    kill_processes()
    delete_local_folders()
    update_extensions_json()
    clean_registry()
    broadcast_env_change()
    print("=== Codex Residue Cleanup Finished ===")

if __name__ == '__main__':
    main()
