from neo4j import GraphDatabase

uri = "neo4j+s://85d1c4a5.databases.neo4j.io"
user = "85d1c4a5"
pwd = "zGULXj7cn01khbESX8U2ffmmCu8sG6pYJhPP6TF9-X8"

print(f"Trying Aura: {uri} ...")
try:
    driver = GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=5.0)
    driver.verify_connectivity()
    print("SUCCESS")
    driver.close()
except Exception as e:
    print(f"FAILED: {e}")
