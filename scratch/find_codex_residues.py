import os
import winreg
import sys
import json
import subprocess

def search_folders():
    paths = [
        os.path.expandvars(r'%USERPROFILE%\.codex'),
        os.path.expandvars(r'%APPDATA%\Codex'),
        os.path.expandvars(r'%LOCALAPPDATA%\Codex'),
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Codex'),
        r'C:\Program Files\Codex',
        r'C:\Program Files (x86)\Codex'
    ]
    
    found = []
    for p in paths:
        if os.path.exists(p):
            found.append(('folder', p))
            
    # Search vscode extensions
    vscode_ext_dir = os.path.expandvars(r'%USERPROFILE%\.vscode\extensions')
    if os.path.exists(vscode_ext_dir):
        try:
            for item in os.listdir(vscode_ext_dir):
                if 'codex' in item.lower():
                    found.append(('vscode_extension', os.path.join(vscode_ext_dir, item)))
        except Exception as e:
            print(f"Error reading vscode extensions: {e}")
            
    return found

def search_registry():
    found_keys = []
    
    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
    ]
    
    for root, subkey in roots:
        try:
            with winreg.OpenKey(root, subkey) as key:
                info = winreg.QueryInfoKey(key)
                for i in range(info[0]): # subkeys
                    try:
                        name = winreg.EnumKey(key, i)
                        if 'codex' in name.lower():
                            path = f"{'HKCU' if root == winreg.HKEY_CURRENT_USER else 'HKLM'}\\{subkey}\\{name}"
                            found_keys.append(('registry_key', path))
                    except OSError:
                        continue
        except OSError:
            continue
            
    return found_keys

def search_vscode_settings():
    settings_path = os.path.expandvars(r'%APPDATA%\Code\User\settings.json')
    found = []
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Find any keys containing 'codex'
            keys_to_remove = [k for k in data.keys() if 'codex' in k.lower()]
            if keys_to_remove:
                found.append(('vscode_settings_keys', settings_path, keys_to_remove))
        except Exception as e:
            print(f"Error reading VS Code settings: {e}")
    return found

def search_running_processes():
    found = []
    try:
        # Get list of running processes containing codex
        cmd = 'powershell -Command "Get-Process | Where-Object { $_.ProcessName -like \'*codex*\' } | Select-Object -Property Id, ProcessName, Path | ConvertTo-Json"'
        res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if res.returncode == 0 and res.stdout.strip():
            try:
                proc_data = json.loads(res.stdout)
                if isinstance(proc_data, dict):
                    proc_data = [proc_data]
                for p in proc_data:
                    found.append(('process', f"PID {p.get('Id')}: {p.get('ProcessName')} ({p.get('Path')})", p.get('Id')))
            except Exception as e:
                pass
    except Exception as e:
        print(f"Error searching running processes: {e}")
    return found

def search_env_vars():
    found = []
    for k, v in os.environ.items():
        if 'codex' in k.lower() or 'codex' in v.lower():
            found.append(('env_var', f"{k}={v}"))
    return found

def main():
    print("--- Searching for Codex residues ---")
    
    # 1. Folders
    folders = search_folders()
    for t, p in folders:
        print(f"FOUND: [{t}] {p}")
        
    # 2. Registry
    keys = search_registry()
    for t, p in keys:
        print(f"FOUND: [{t}] {p}")
        
    # 3. VS Code settings
    vscode_settings = search_vscode_settings()
    for t, p, keys_to_remove in vscode_settings:
        print(f"FOUND: [{t}] in {p} (keys: {keys_to_remove})")
        
    # 4. Running processes
    processes = search_running_processes()
    for t, p, pid in processes:
        print(f"FOUND: [{t}] {p}")
        
    # 5. Env vars
    env_vars = search_env_vars()
    for t, p in env_vars:
        print(f"FOUND: [{t}] {p}")
        
    if not (folders or keys or vscode_settings or processes or env_vars):
        print("No Codex residues found in common locations.")

if __name__ == '__main__':
    main()
