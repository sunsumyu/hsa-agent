import requests
import json
import time

URL = "http://127.0.0.1:18081/ims-fqz/agent/chat"
SESSION_ID = "robustness-test-session-1"

def chat(message, timeout=180, stream=True):
    print(f"\n[QUERY] {message}")
    headers = {
        "Content-Type": "application/json",
        "X-Session-Id": SESSION_ID
    }
    try:
        response = requests.post(URL, data=json.dumps(message), headers=headers, stream=stream, timeout=timeout)
        if response.status_code != 200:
            print(f"[FAIL] HTTP {response.status_code}: {response.text}")
            return False
            
        full_text = ""
        for line in response.iter_lines():
            if line:
                chunk = line.decode('utf-8')
                full_text += chunk
                print(chunk, end="", flush=True)
        print("\n[SUCCESS]")
        return True
    except Exception as e:
        print(f"\n[INTERRUPTED] {e}")
        return False

def test_suite():
    print("=== STARTING 5-ROUND ROBUSTNESS TEST ===")
    
    # 1. Success 1
    chat("列出所有审计表")
    
    # 2. Success 2
    chat("查询 fqz_all_yy_yd_1 的字段结构")
    
    # 3. INTERRUPT
    print("\n[SIMULATING INTERRUPTION] Testing partial turn recovery...")
    try:
        # Intentionally short timeout to simulate a network cut mid-SQL execution
        requests.post(URL, data=json.dumps("查询近1年费用超过10万的记录"), headers={"X-Session-Id": SESSION_ID}, timeout=5)
    except Exception:
        print("[INTERRUPTED] Simulated session cut during tool execution.")
    
    # 4. Success 3 (Recovery)
    print("\n[RECOVERY TEST] Starting next turn after interruption...")
    chat("总结一下目前的高风险案例")
    
    # 5. Success 4 & 5
    chat("查询福州地区的医院分布")
    chat("给我最后一张审计报告的建议")
    
    print("\n=== ROBUSTNESS TEST COMPLETE ===")

if __name__ == "__main__":
    test_suite()
