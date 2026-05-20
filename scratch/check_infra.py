import socket
import os
from dotenv import load_dotenv
load_dotenv()

def test_conn(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        print(f"FAILED {host}:{port} -> {e}")
        return False

print("--- Infrastructure Health Check ---")
# 1. ClickHouse
test_conn("localhost", 8123)
# 2. Redis
test_conn("localhost", 6379)
# 3. Neo4j Aura
neo4j_uri = os.getenv("NEO4J_URI", "")
if "databases.neo4j.io" in neo4j_uri:
    host = neo4j_uri.split("//")[1].split(":")[0]
    test_conn(host, 7687)
# 4. Langfuse
test_conn("cloud.langfuse.com", 443)
# 5. Phoenix
test_conn("127.0.0.1", 4517)
