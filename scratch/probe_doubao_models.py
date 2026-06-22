"""
扩大扫描：火山引擎带日期后缀的官方 Serverless 模型名
"""
import os, sys
from dotenv import load_dotenv
load_dotenv()

# 带日期后缀的完整模型名（官方格式）
CANDIDATE_MODELS = [
    # Doubao-Seed-1.8 系列
    "doubao-seed-1-8",
    "doubao-seed-1-8-0607",
    "doubao-seed-1-8-250525",
    "doubao-seed-1-8-250118",
    # Doubao-Seed-1.6 系列
    "doubao-seed-1-6",
    "doubao-seed-1-6-250115",
    "doubao-seed-1-6-lite",
    "doubao-seed-1-6-lite-250115",
    "doubao-seed-1-8-lite",
    "doubao-seed-1-8-lite-250525",
    # Doubao-1.5 系列
    "doubao-1-5-pro-32k-250115",
    "doubao-1-5-pro-128k-250115",
    "doubao-1-5-lite-32k-250115",
    "doubao-1-5-thinking-pro-32k-250415",
    "doubao-1-5-thinking-pro-128k-250415",
    "doubao-1-5-vision-pro-32k-250115",
    # Doubao Pro 系列 (旧版)
    "doubao-pro-32k-240115",
    "doubao-pro-32k-241215",
    "doubao-pro-128k-240115",
    "doubao-pro-4k-240515",
    "doubao-lite-32k-240115",
    "doubao-lite-128k-240115",
    "doubao-lite-4k-240515",
    # Doubao character
    "doubao-character-pro-32k-240901",
    "doubao-character-lite-32k-240901",
    # DeepSeek-R1 火山版
    "deepseek-r1-250120",
    "deepseek-r1-distill-qwen-32b-250120",
    # GLM 系列
    "glm-4-plus",
    "glm-4-flash",
]

def test_model(model_name, api_key, base_url):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "1+1=?"}],
            max_tokens=20,
            timeout=8,
        )
        answer = resp.choices[0].message.content.strip()[:50]
        return True, answer
    except Exception as e:
        err = str(e)
        if "not found" in err.lower() or "does not exist" in err.lower() or "invalid model" in err.lower() or "No such model" in err:
            return False, "不存在"
        if "SetLimitExceeded" in err:
            return False, "安全限额(deepseek-v3-2)"
        if "Insufficient Balance" in err or "402" in err:
            return False, "余额不足"
        if "Connection error" in err:
            return False, "连接失败"
        return False, err[:100]

def main():
    api_key = os.getenv("VOLC_API_KEY")
    base_url = os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    print(f"base_url={base_url}\n")

    ok_models = []
    for model in CANDIDATE_MODELS:
        ok, msg = test_model(model, api_key, base_url)
        tag = "OK  " if ok else "FAIL"
        print(f"  [{tag}] {model:<45} {msg}")
        if ok:
            ok_models.append((model, msg))

    print(f"\n{'='*60}")
    print(f"可用模型 ({len(ok_models)}):")
    for m, r in ok_models:
        print(f"  + {m}  -> 回复: {r}")

if __name__ == "__main__":
    main()
