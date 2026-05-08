from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

# 尝试使用 neo4j:// 协议替代 neo4j+s://
uri = "neo4j://85d1c4a5.databases.neo4j.io"
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

print(f"正在尝试连接 (neo4j://): {uri}")
try:
    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=10.0)
    driver.verify_connectivity()
    print("✅ SUCCESS: 成功连接至 Aura 云端图数据库！")
    driver.close()
except Exception as e:
    print(f"❌ FAILED: {e}")
