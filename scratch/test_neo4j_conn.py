from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

# 从 .env 读取配置
uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

print(f"正在尝试连接从 hello-agents 获取的 Neo4j Aura: {uri}")
try:
    # 设置 5 秒超时，防止 hang 住
    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5.0)
    driver.verify_connectivity()
    print("✅ SUCCESS: 成功连接至 Aura 云端图数据库！")
    driver.close()
except Exception as e:
    print(f"❌ FAILED: {e}")
