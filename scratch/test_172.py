from neo4j import GraphDatabase

uri = "bolt://172.18.27.30:7687"
user = "neo4j"
passwords = ["test@123", "62901990552", "password", "neo4j"]

for pwd in passwords:
    print(f"Trying {user} / {pwd} ...")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=3.0)
        driver.verify_connectivity()
        print(f"SUCCESS: Connected with {pwd}")
        driver.close()
        break
    except Exception as e:
        print(f"FAILED: {e}")
