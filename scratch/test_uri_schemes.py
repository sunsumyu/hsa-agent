from neo4j import GraphDatabase

uris = ["bolt://172.18.27.30:7687", "neo4j://172.18.27.30:7687", "neo4j+s://172.18.27.30:7687", "neo4j+ssc://172.18.27.30:7687"]
user = "neo4j"
pwd = "password"  # Start with default

for uri in uris:
    print(f"Trying URI: {uri}")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=3.0)
        driver.verify_connectivity()
        print(f"SUCCESS: Connected with {uri}")
        driver.close()
        break
    except Exception as e:
        print(f"FAILED: {type(e).__name__} - {e}")
