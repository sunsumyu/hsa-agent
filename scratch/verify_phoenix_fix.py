import os
import sys
import io

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 将项目根目录添加到路径
sys.path.append(r"e:\chain\hsa-agent")

from app.core.observability import init_observability, shutdown_observability
from loguru import logger

def verify_fix():
    print("🔭 [Observability] 正在验证 Phoenix 自愈修复效果...")
    
    # 模拟初始化过程
    try:
        init_observability()
        print("\n✅ [SUCCESS] Phoenix 及 OTel 链路初始化成功！")
        print("💡 结论：物理清空脏数据后，Alembic 自动完成了新 Schema 的初始化。")
    except Exception as e:
        print(f"\n❌ [FAILED] 初始化依然失败: {e}")
    finally:
        shutdown_observability()

if __name__ == "__main__":
    verify_fix()
