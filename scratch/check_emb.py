import requests
try:
    r = requests.head("https://hf-mirror.com/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", allow_redirects=False, timeout=5)
    print(f"Status: {r.status_code}")
except Exception as e:
    print(e)
