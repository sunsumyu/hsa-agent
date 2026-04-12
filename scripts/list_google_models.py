import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_google_models():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in .env")
        return
    
    try:
        client = genai.Client(api_key=api_key)
        print("--- Available Google Models ---")
        # 尝试列出模型
        for model in client.models.list():
            print(f"Model ID: {model.name}, Display Name: {model.display_name}")
    except Exception as e:
        print(f"Failed to list models: {e}")

if __name__ == "__main__":
    list_google_models()
