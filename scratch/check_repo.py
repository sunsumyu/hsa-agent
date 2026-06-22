import requests
try:
    r = requests.head("https://hf-mirror.com/sentence-transformers/clip-ViT-B-32", allow_redirects=True, timeout=5)
    print(f"Status: {r.status_code}")
    print(f"URL: {r.url}")
except Exception as e:
    print(e)
