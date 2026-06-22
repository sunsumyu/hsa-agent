import asyncio
import os
import sys
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())

from app.infra.model_manager import model_manager
from langchain_core.messages import HumanMessage

async def probe_specific_models():
    target_models = ["doubao-pro-32k", "doubao-smart"]
    print(f">>> [专项拨测] 正在验证: {target_models}")
    
    for m_id in target_models:
        try:
            print(f"\n--- 正在探测 {m_id} ---")
            cfg = model_manager.providers.get(m_id)
            if not cfg:
                print(f"❌ 找不到配置: {m_id}")
                continue
                
            llm = model_manager._create_llm(m_id, cfg, bypass_limit=True)
            if not llm:
                print(f"❌ 无法创建 LLM 实例: {m_id}")
                continue
            
            # 使用绑定 max_tokens 的方式快速测试
            resp = await llm.ainvoke([HumanMessage(content="hi")], config={"max_tokens": 10})
            print(f"✅ {m_id} 响应成功: {resp.content[:50]}...")
        except Exception as e:
            print(f"❌ {m_id} 探测失败: {e}")

if __name__ == "__main__":
    asyncio.run(probe_specific_models())
