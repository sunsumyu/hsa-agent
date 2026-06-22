import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.getenv("BAILIAN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

test_models = [
    "qwen-turbo",
    "qwen-plus",
    "qwen-max",
    "qwen-long",
    "qwen-vl-max",
    "qwen-max-longcontext"
]

print("--- 百炼可用口径扫描 ---")
for model in test_models:
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5
        )
        print(f"[OK] {model}: 调用成功")
    except Exception as e:
        if "403" in str(e) or "Quota" in str(e):
            print(f"[FAIL] {model}: 额度耗尽")
        else:
            print(f"[FAIL] {model}: {str(e)[:50]}...")
