import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD")

print(f"Connecting to: {uri}")

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("✅ Connection Successful!")
    
    with driver.session() as session:
        result = session.run("RETURN 1 AS one")
        print(f"Test Query Result: {result.single()['one']}")
        
    driver.close()
except Exception as e:
    print(f"❌ Connection Failed: {e}")
