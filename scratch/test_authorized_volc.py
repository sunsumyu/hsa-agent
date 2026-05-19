from app.infra.model_manager import model_manager
from app.infra.usage_tracker import usage_tracker
from dotenv import load_dotenv
import os

load_dotenv()

def test_fixed_volc():
    model_id = "doubao-pro-32k"
    # 强制清理内存黑名单
    if model_id in usage_tracker.model_configs:
        usage_tracker.model_configs[model_id].is_active = True
        print(f"Force activated {model_id}")
    
    cfg = model_manager.providers.get(model_id)
    print(f"Calling endpoint: {cfg.model_name}")
    
    try:
        llm = model_manager._create_llm(model_id, cfg)
        res = llm.invoke("Hello, say 'READY'")
        print(f"Full response: {res.content}")
        if "READY" in res.content.upper():
            print("✅ TEST PASSED: Connection successful!")
        else:
            print("⚠️ Connected but unexpected response.")
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")

if __name__ == "__main__":
    test_fixed_volc()
