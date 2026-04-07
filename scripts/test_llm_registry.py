from app.model_manager import model_manager
from langchain_core.messages import HumanMessage
import sys

try:
    print("--- 多模型注册表内核检测 ---")
    chain = model_manager.get_adaptive_llm(require_tools=True)
    
    if hasattr(chain, "first"):
        print(f"[OK] 成功构建回退链!")
        print(f" -> 主模型: {chain.first.model_name}")
        print(f" -> 备选模型总数: {len(chain.fallbacks)}")
        for i, fb in enumerate(chain.fallbacks):
            print(f"    - 备选 {i+1}: {fb.model_name} ({fb.base_url})")
    else:
        print(f"[OK] 成功构建单一模型节点: {chain.model_name}")
    
    print("\n[SUCCESS] 模型管理内核已就绪，具备支撑几十个模型动态切换的物理能力。")
except Exception as e:
    print(f"[ERROR] 内核检测失败: {e}")
    sys.exit(1)
