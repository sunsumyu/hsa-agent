import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "0"
from sentence_transformers import SentenceTransformer
import time

print("Starting model download/load test...")
t0 = time.time()
try:
    model = SentenceTransformer('clip-ViT-B-32')
    print(f"SUCCESS! Loaded in {time.time()-t0:.2f}s")
except Exception as e:
    print(f"FAILED: {e}")
