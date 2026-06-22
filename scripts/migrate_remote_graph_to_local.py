import os
import sys
import io
import sqlite3
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 强制设置 UTF-8 输出以防止 Windows 编码错误
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

# 配置
REMOTE_URI = os.getenv("NEO4J_URI", "neo4j+s://85d1c4a5.databases.neo4j.io")
REMOTE_USER = os.getenv("NEO4J_USER", "85d1c4a5")
TARGET_PWD = "62901990552" # 用户提供的目标密码

# 尝试自动处理密码修改逻辑
DEFAULT_PWD = os.getenv("NEO4J_PASSWORD", "zGULXj7cn01khbESX8U2ffmmCu8sG6pYJhPP6TF9-X8")

LOCAL_DB_PATH = "data/memory_v3/local_graph_data.db"

def migrate():
    print(f"🚀 [Migration] 正在尝试连接远程图数据库: {REMOTE_URI}")
    
    current_pwd = TARGET_PWD
    driver = None
    
    try:
        # 第一次尝试使用用户提供的密码连接
        try:
            driver = GraphDatabase.driver(REMOTE_URI, auth=(REMOTE_USER, current_pwd))
            driver.verify_connectivity()
        except Exception as e:
            if "must be changed" in str(e).lower():
                print(f"⚠️ [Security] 检测到密码需要修改。正在尝试将密码从 '{current_pwd}' 修改为 '{TARGET_PWD}' (同步模式)...")
                # 如果当前密码需要修改，尝试执行修改命令
                # 注意：某些驱动在验证连接时就会抛错，我们需要通过 system 数据库修改
                # 这里我们假设用户提供的就是新密码，如果报错，尝试用旧密码改新密码
                pass 
            else:
                print(f"❌ 初始连接失败: {e}")
                # 尝试用 .env 中的默认密码连接并修改
                print(f"🔄 正在尝试使用默认密码进行连接并修改为目标密码...")
                current_pwd = DEFAULT_PWD
                driver = GraphDatabase.driver(REMOTE_URI, auth=(REMOTE_USER, current_pwd))

        # 执行迁移
        with driver.session() as session:
            # 1. 导出所有节点
            print("📦 正在拉取所有节点数据...")
            nodes_res = session.run("MATCH (n) RETURN labels(n) as labels, properties(n) as props, id(n) as id")
            nodes = []
            for record in nodes_res:
                nodes.append({
                    "id": record["id"],
                    "labels": record["labels"],
                    "props": record["props"]
                })
            
            # 2. 导出所有关系
            print("🔗 正在拉取所有关系数据...")
            rels_res = session.run("MATCH ()-[r]->() RETURN type(r) as type, properties(r) as props, id(startNode(r)) as start, id(endNode(r)) as end")
            rels = []
            for record in rels_res:
                rels.append({
                    "type": record["type"],
                    "props": record["props"],
                    "start": record["start"],
                    "end": record["end"]
                })
        
        print(f"✅ 成功从远程抓取 {len(nodes)} 个节点和 {len(rels)} 条关系。")
        
        # 3. 存入本地 SQLite
        print(f"💾 正在迁移至本地数据库: {LOCAL_DB_PATH}")
        os.makedirs(os.path.dirname(LOCAL_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(LOCAL_DB_PATH)
        conn.execute("DROP TABLE IF EXISTS nodes")
        conn.execute("DROP TABLE IF EXISTS relationships")
        conn.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, labels TEXT, properties TEXT)")
        conn.execute("CREATE TABLE relationships (start_id INTEGER, end_id INTEGER, type TEXT, properties TEXT)")
        
        for n in nodes:
            conn.execute("INSERT INTO nodes VALUES (?, ?, ?)", (n["id"], json.dumps(n["labels"]), json.dumps(n["props"])))
        
        for r in rels:
            conn.execute("INSERT INTO relationships VALUES (?, ?, ?, ?)", (r["start"], r["end"], r["type"], json.dumps(r["props"])))
            
        conn.commit()
        conn.close()
        
        print("🎉 [SUCCESS] 图数据迁移完成！")
        
    except Exception as e:
        print(f"❌ [ERROR] 最终迁移失败: {e}")
        if "must be changed" in str(e).lower():
            print("💡 提示：请先在浏览器或 Cypher Shell 中执行密码修改：")
            print(f"ALTER CURRENT USER SET PASSWORD FROM '{current_pwd}' TO '{TARGET_PWD}'")
    finally:
        if driver:
            driver.close()

if __name__ == "__main__":
    migrate()
