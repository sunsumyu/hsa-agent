from neo4j import GraphDatabase

uri = "bolt://172.18.27.30:7687"
user = "neo4j"
pwd = "test@123"

print(f"Trying {uri} with {user} / {pwd} ...")
try:
    driver = GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=5.0)
    driver.verify_connectivity()
    print("SUCCESS")
    driver.close()
except Exception as e:
    print(f"FAILED: {e}")
