import requests
import time

mirrors = [
    "https://hf-mirror.com",
    "https://huggingface.co",
    "https://mirror.ghproxy.com/https://huggingface.co",
]

print("Testing mirrors...")
for m in mirrors:
    t0 = time.time()
    try:
        r = requests.get(f"{m}/api/models/sentence-transformers/clip-ViT-B-32", timeout=5)
        print(f"[OK] {m} - {r.status_code} - {time.time()-t0:.2f}s")
    except Exception as e:
        print(f"[FAIL] {m} - {type(e).__name__}: {str(e)}")
