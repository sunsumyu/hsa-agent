from app.model_manager import model_manager
from app.schemas import ModelConfig
import os
from dotenv import load_dotenv

load_dotenv()

def test_volc():
    model_id = "doubao-pro-32k"
    cfg = model_manager.providers.get(model_id)
    if not cfg:
        print(f"Error: {model_id} not found in config")
        return
    
    print(f"Testing {model_id} with endpoint: {cfg.model_name}")
    llm = model_manager._create_llm(model_id, cfg)
    if llm:
        print("✅ Model instantiation successful!")
    else:
        print("❌ Model instantiation failed!")

if __name__ == "__main__":
    test_volc()
