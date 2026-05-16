import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

URI = os.getenv("NEO4J_URI", "neo4j+s://85d1c4a5.databases.neo4j.io")
USER = os.getenv("NEO4J_USER", "85d1c4a5")
CURRENT_PWD = os.getenv("NEO4J_PASSWORD", "zGULXj7cn01khbESX8U2ffmmCu8sG6pYJhPP6TF9-X8")
NEW_PWD = "62901990552" # 用户提供的目标密码

def reset_password():
    print(f"🔒 [Security] 正在尝试为租户 {USER} 重置 Neo4j 初始密码...")
    
    try:
        # 使用当前密码连接
        driver = GraphDatabase.driver(URI, auth=(USER, CURRENT_PWD))
        with driver.session(database="system") as session:
            # 执行密码修改命令
            session.run(f"ALTER CURRENT USER SET PASSWORD FROM '{CURRENT_PWD}' TO '{NEW_PWD}'")
        
        print(f"✅ [SUCCESS] 密码已成功修改为: {NEW_PWD}")
        print("💡 请记得之后使用新密码进行登录。")
        driver.close()
        return True
    except Exception as e:
        if "must be changed" in str(e).lower() or "CredentialsExpired" in str(e):
             # 某些环境下需要特殊处理，尝试直接使用驱动的变更机制（如果支持）
             print(f"⚠️ 正在处理强制变更逻辑...")
        else:
            print(f"❌ 密码修改失败: {e}")
        return False

if __name__ == "__main__":
    reset_password()
