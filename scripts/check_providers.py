import os
import requests
import sys
from dotenv import load_dotenv

# Ensure app is importable
sys.path.append(os.getcwd())

from app.model_manager import model_manager

load_dotenv()

def check_provider(model_id):
    print(f"--- Testing {model_id} ---")
    try:
        from langchain_core.messages import HumanMessage
        llm, _ = model_manager.get_adaptive_llm(model_id=model_id)
        # Try a simple prompt
        res = llm.invoke([HumanMessage(content="1+1")])
        print(f"SUCCESS: {res.content}")
        return True
    except Exception as e:
        print(f"FAILURE: {e}")
        return False

if __name__ == "__main__":
    providers = ["qwen-max", "qwen-plus", "doubao-pro-32k", "gemma-4-31b-it"]
    for p in providers:
        check_provider(p)
