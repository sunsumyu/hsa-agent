import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def test_raw_volc():
    api_key = os.getenv("VOLC_API_KEY")
    base_url = os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    
    # 新 ID
    endpoints = ["ep-20260414173115-j9m9b", "ep-20260414173509-29rc8"]
    
    print(f">>> [原生接口测试] BaseURL: {base_url}")
    
    for ep in endpoints:
        print(f"\n--- 测试 Endpoint: {ep} ---")
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": ep,
            "messages": [
                {"role": "user", "content": "hi"}
            ],
            "max_tokens": 10
        }
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                print(f"SUCCESS! Response: {resp.json()['choices'][0]['message']['content']}")
            else:
                print(f"FAILED (HTTP {resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"EXCEPTION: {str(e)}")

if __name__ == "__main__":
    test_raw_volc()
