import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import sys
from loguru import logger

def verify_mirror():
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        endpoint = api.endpoint
        logger.info(f"🔍 物理验证：当前 HfApi 锁定的镜像站地址为: {endpoint}")
        
        if "hf-mirror.com" not in endpoint:
            logger.error("❌ 验证失败：ENDPOINT 未指向镜像站！")
            return False
            
        # 尝试获取模型元数据
        model_id = "clip-ViT-B-32"
        info = api.model_info("sentence-transformers/clip-ViT-B-32") # model_info requires the full repo ID, but SentenceTransformer needs the short one.
        logger.success(f"✅ 物理验证成功：已成功从 {endpoint} 获取模型 {model_id} 的元数据。")
        return True
    except Exception as e:
        logger.error(f"❌ 物理验证崩溃: {e}")
        return False

if __name__ == "__main__":
    verify_mirror()
