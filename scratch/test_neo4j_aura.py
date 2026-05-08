import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
pwd = os.getenv("NEO4J_PASSWORD")

print(f"--- Neo4j Connectivity Test (No Emojis) ---")

def test_conn():
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=10.0)
        driver.verify_connectivity()
        print("SUCCESS: Connected to Neo4j Aura!")
        
        with driver.session() as session:
            result = session.run("RETURN 'Connection Verified' as msg")
            record = result.single()
            print(f"Query Result: {record['msg']}")
            
        driver.close()
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_conn()
