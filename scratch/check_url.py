import requests
try:
    r = requests.head("https://hf-mirror.com/sentence-transformers/clip-ViT-B-32/resolve/main/modules.json", timeout=5)
    print(r.status_code)
except Exception as e:
    print(e)
