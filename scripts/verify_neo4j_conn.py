import os
import sys
from loguru import logger
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logger.warning("未安装 python-dotenv，尝试直接读取环境变量")

# 将项目根目录加入路径
sys.path.append(os.getcwd())

def verify_neo4j():
    logger.info("🚀 开始 Neo4j 远程云端链路深度验证...")
    
    # 1. 检查环境变量
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not uri or "databases.neo4j.io" not in uri:
        logger.error(f"❌ 环境变量加载失败或 URI 非云端格式。当前 URI: {uri}")
        return

    logger.info(f"配置核查: 正在连接云端实例 {uri}, 用户: {user}")

    try:
        from app.neo4j_manager import neo4j_manager
        
        # 强制触发连接
        logger.info("正在尝试建立物理连接 (这可能需要 30-60 秒，如果 AuraDB 正在唤醒)...")
        driver = neo4j_manager.get_driver()
        
        with driver.session() as session:
            logger.info("正在执行云端元数据探测 (CALL db.labels())...")
            result = session.run("CALL db.labels()")
            labels = [record["label"] for record in result]
            
            logger.success(f"✅ Neo4j 云端连接成功！")
            logger.info(f"云端数据库中的标签: {labels}")
            
    except Exception as e:
        logger.error(f"❌ 验证失败: {e}")
        if "routing" in str(e).lower():
            logger.warning("提示：路由失败通常意味着 AuraDB 实例正在休眠，请尝试再次运行脚本以等待其唤醒。")
        sys.exit(1)

if __name__ == "__main__":
    verify_neo4j()
