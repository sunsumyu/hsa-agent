"""
测试 Doubao 1.5 模型的 tool calling 支持
"""
import os
from dotenv import load_dotenv
load_dotenv()

MODELS = [
    "doubao-1-5-pro-32k-250115",
    "doubao-1-5-lite-32k-250115",
    "doubao-seed-1-6",
]

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    }
}

def test_tools(model, api_key, base_url):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
            tools=[TOOL],
            tool_choice="auto",
            max_tokens=100,
            timeout=12,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            return True, f"调用工具: {tc.function.name}({tc.function.arguments[:60]})"
        else:
            return False, f"未调工具，直接回复: {(msg.content or '')[:80]}"
    except Exception as e:
        return False, f"ERROR: {str(e)[:120]}"

def main():
    api_key = os.getenv("VOLC_API_KEY")
    base_url = os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    
    print("测试 Tool Calling 支持\n")
    for model in MODELS:
        ok, msg = test_tools(model, api_key, base_url)
        tag = "TOOLS OK" if ok else "NO TOOLS"
        print(f"  [{tag}] {model}")
        print(f"           {msg}\n")

if __name__ == "__main__":
    main()
