import os
import requests
import json
from loguru import logger
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# 强制重新加载 .env
load_dotenv(override=True)

def load_system_all_data():
    """从本地文件加载系统统计数据和配置数据"""
    try:
        stats_path = "e:/chain/hsa-agent-python/data/usage_stats.json"
        config_path = "e:/chain/hsa-agent-python/app/llm_providers.json"
        
        stats = {}
        if os.path.exists(stats_path):
            with open(stats_path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
        
        configs = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                configs = json.load(f)
                
        return stats, configs
    except Exception as e:
        print(f"[-] 无法读取系统账本: {e}")
        return {}, {}

def find_config_by_model_name(model_name: str, configs: dict):
    """
    由于统计文件通常使用 Top-Level Key (如 qwen-long)，
    而探测时可能使用具体的 model_name (如 ep-m-xxx)，
    这里做一个反向查找。
    """
    for entry_id, cfg in configs.items():
        if cfg.get("model_name") == model_name or entry_id == model_name:
            return entry_id, cfg
    return None, None

def test_deepseek_balance():
    """测试 DeepSeek 余额查询 (物理实时)"""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DS_API_KEY")
    if not api_key:
        print("[-] DeepSeek: 未配置 API_KEY，跳过物理查询。")
        return
    
    url = "https://api.deepseek.com/user/balance"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            balance = data.get("balance_infos", [{}])[0].get("total_balance", "0")
            print(f"[+] DeepSeek 物理余额: ￥{balance}")
        else:
            print(f"[-] DeepSeek 余额查询失败: {response.text}")
    except Exception as e:
        print(f"[-] DeepSeek 异常: {e}")

async def micro_probe(probe_id: str, platform_name: str, base_url: str, api_key_env: str, stats: dict, configs: dict):
    """通过微探测来测试配额，并展示今日/累计用量"""
    api_key = os.getenv(api_key_env)
    
    # 查找匹配的配置
    entry_id, cfg = find_config_by_model_name(probe_id, configs)
    
    # 获取统计
    daily_used = 0
    total_used = 0
    limit = 0
    
    if entry_id:
        daily_used = stats.get("daily_usage", {}).get(entry_id, 0)
        total_used = stats.get("total_usage", {}).get(entry_id, 0)
        limit = cfg.get("daily_quota", 0)
    
    pct = (daily_used / limit * 100) if limit > 0 else 0
    
    print(f"\n[*] {platform_name} (探测 ID: {probe_id})")
    print(f"    📅 今日消耗: {daily_used:,} tokens / 上限 {limit:,} tokens ({pct:.2f}%)")
    print(f"    📈 累计消耗: {total_used:,} tokens (全生命周期)")

    # 物理探测
    if not api_key:
        print(f"    [-] 未配置 {api_key_env}，跳过物理拨测。")
        return

    try:
        llm = ChatOpenAI(
            model=probe_id,
            api_key=api_key,
            base_url=base_url,
            max_tokens=1,
            request_timeout=20
        )
        await llm.ainvoke([HumanMessage(content="1")])
        print(f"    [+] 物理探测: 正常 (HTTP 200)")
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "exhausted" in err_msg.lower():
            print(f"    [!] 物理探测: 熔断 (HTTP 403 - 平台侧已耗尽)")
        else:
            print(f"    [-] 物理探测: 异常 - {err_msg}")

async def main():
    print("="*60)
    print("HSA Agent 算力透视工具 V1.6 - 【多维账本分析】")
    print("="*60)
    
    stats, configs = load_system_all_data()
    
    # 1. DeepSeek
    test_deepseek_balance()
    
    # 2. 百炼 (针对 qwen-max)
    await micro_probe(
        probe_id="qwen-max",
        platform_name="阿里云百炼",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="BAILIAN_API_KEY",
        stats=stats,
        configs=configs
    )
    
    # 3. 火山引擎 (针对 ep-xxx)
    await micro_probe(
        probe_id="ep-m-20260409000028-vhkbw", 
        platform_name="火山引擎",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key_env="VOLC_API_KEY",
        stats=stats,
        configs=configs
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
