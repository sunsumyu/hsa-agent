import os
import sys
import io

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 将项目根目录添加到路径
sys.path.append(r"e:\chain\hsa-agent")

from app import observability
from loguru import logger

def verify_fix():
    print("🔭 [Observability] 正在执行【二次】验证...")
    
    # 清理可能的单例残留
    observability._phoenix_session = None
    observability._tracer_provider = None
    
    try:
        observability.init_observability()
        
        # 显式检查 session 是否创建成功
        if observability._phoenix_session is not None:
            print("\n🚀 [SUCCESS] Phoenix 采集器已成功启动！")
            print(f"URL: {observability._phoenix_session.url}")
        else:
            print("\n❌ [FAILED] init_observability 执行完成但未检测到活跃 Session。")
            
    except Exception as e:
        print(f"\n❌ [ERROR] 初始化捕获到致命异常: {e}")
    finally:
        observability.shutdown_observability()

if __name__ == "__main__":
    verify_fix()
