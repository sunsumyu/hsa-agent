import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def debug_smart_router_metadata():
    api_key = os.getenv("VOLC_API_KEY")
    base_url = os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    
    # 使用你的 Smart Router ID
    endpoint = "ep-20260414173115-j9m9b"
    
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": endpoint,
        "messages": [{"role": "user", "content": "写一段 Python 代码计算斐波那契数列"}], # 稍微复杂的任务，诱导它用大模型
        "max_tokens": 100
    }
    
    print(f">>> [元数据侦探] 正在拨号智能路由...")
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    
    if resp.status_code == 200:
        data = resp.json()
        print("\n--- 原始响应 JSON (部分) ---")
        # 看看 model 字段是否被替换成了真实模型，或者有没有其它 metadata
        print(f"Model 字段显示: {data.get('model')}")
        
        # 打印所有 headers，看看有没有隐藏信息
        print("\n--- 响应头 (Headers) ---")
        for k, v in resp.headers.items():
            if "model" in k.lower() or "ark" in k.lower():
                print(f"{k}: {v}")
    else:
        print(f"请求失败: {resp.text}")

if __name__ == "__main__":
    debug_smart_router_metadata()
