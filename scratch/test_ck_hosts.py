import os
import socket
import clickhouse_connect
import clickhouse_driver

def test_socket(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            if s.connect_ex((host, port)) == 0:
                return True
    except Exception:
        pass
    return False

def test_http_client(host, port):
    try:
        client = clickhouse_connect.get_client(host=host, port=port, connect_timeout=3)
        client.query("SELECT 1")
        return True, "Connected successfully"
    except Exception as e:
        return False, str(e)

def test_native_client(host, port):
    try:
        client = clickhouse_driver.Client(host=host, port=port, connect_timeout=3)
        client.execute("SELECT 1")
        return True, "Connected successfully"
    except Exception as e:
        return False, str(e)

def run_diagnostics():
    targets = [
        ("172.28.4.37", 9000),
        ("172.28.4.37", 8123),
        ("127.0.0.1", 9000),
        ("127.0.0.1", 8123),
        ("localhost", 9000),
        ("localhost", 8123),
    ]
    
    print("=== ENVIRONMENT PROXIES ===")
    print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')}")
    print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')}")
    print(f"NO_PROXY: {os.environ.get('NO_PROXY') or os.environ.get('no_proxy')}")
    
    print("\n=== SOCKET PORT REACHABILITY ===")
    for host, port in targets:
        reachable = test_socket(host, port)
        print(f"Socket {host}:{port} -> {'REACHABLE' if reachable else 'UNREACHABLE'}")
        
    print("\n=== CLICKHOUSE DRIVER TESTS ===")
    for host, port in targets:
        if not test_socket(host, port):
            continue
        if port == 9000:
            ok, msg = test_native_client(host, port)
            print(f"Native {host}:{port} -> {'SUCCESS' if ok else 'FAILED: ' + msg}")
        else:
            ok, msg = test_http_client(host, port)
            print(f"HTTP {host}:{port} -> {'SUCCESS' if ok else 'FAILED: ' + msg}")

if __name__ == "__main__":
    run_diagnostics()
