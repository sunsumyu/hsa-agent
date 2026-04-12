from app.model_manager import model_manager
import os

def test_lora_registry():
    # 模拟一个本地 LoRA 配置
    model_manager.providers["audit-expert-v1"] = {
        "model_name": "qwen-7b",
        "provider": "local_lora",
        "priority": 1,
        "tools_support": True,
        "base_model_path": "path/to/base",
        "lora_path": "path/to/lora"
    }
    
    print("--- 正在校验 ModelManager 对 LoRA 算力的识别能力 ---")
    models = model_manager.get_model_list()
    expert_found = any(m["id"] == "audit-expert-v1" for m in models)
    
    if expert_found:
        print("[SUCCESS] Found local LoRA expert capability.")
    else:
        print("[FAILURE] Expert capability not found in list.")

if __name__ == "__main__":
    test_lora_registry()
