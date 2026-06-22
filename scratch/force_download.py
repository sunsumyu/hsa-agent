import os
import requests
from tqdm import tqdm
import time

def download_with_resume(url, save_path, proxy):
    proxies = {"http": proxy, "https": proxy}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # 检查已下载的大小
    initial_pos = os.path.getsize(save_path) if os.path.exists(save_path) else 0
    if initial_pos > 0:
        headers["Range"] = f"bytes={initial_pos}-"
        mode = 'ab'
    else:
        mode = 'wb'

    print(f"Resuming download at {initial_pos} bytes...")
    
    try:
        response = requests.get(url, proxies=proxies, stream=True, timeout=30, headers=headers)
        total_size = int(response.headers.get('content-length', 0)) + initial_pos
        
        with open(save_path, mode) as f, tqdm(
            total=total_size, unit='iB', unit_scale=True, initial=initial_pos
        ) as bar:
            for data in response.iter_content(chunk_size=1024*1024):
                if data:
                    f.write(data)
                    bar.update(len(data))
        print("\nSuccess!")
    except Exception as e:
        print(f"\nFailed: {e}")
        return False
    return True

if __name__ == "__main__":
    PROXY = "http://127.0.0.1:7897"
    URL = "https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/pytorch_model.bin"
    SAVE = "C:/Users/AREN/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/blobs/8172c78a05c7438c83f2ff9e4bd38ca37f68262f"
    
    # 自动重试 10 次
    for i in range(10):
        if download_with_resume(URL, SAVE, PROXY):
            break
        print(f"Retrying {i+1}/10...")
        time.sleep(2)
