import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "password")

# Field Alias Registry from app/neo4j_manager.py
FIELD_ALIAS_REGISTRY = [
    {
        "canonical": "fixmedins_code",
        "aliases": ["hosp_code", "hospital_code", "med_ins_code", "org_code", "fixmedins_code"],
        "table": "fqz_fymx_test1",
        "desc": "医疗机构唯一编码",
        "forbidden_aliases": ["hosp_code"]
    },
    {
        "canonical": "fixmedins_name",
        "aliases": ["hosp_name", "hospital_name", "med_ins_name", "fixmedins_name"],
        "table": "fqz_fymx_test1",
        "desc": "医疗机构名称",
        "forbidden_aliases": ["hosp_name"]
    },
    {
        "canonical": "psn_no",
        "aliases": ["patient_id", "person_id", "psn_id", "insured_no", "psn_no"],
        "table": "fqz_fymx_test1",
        "desc": "参保人唯一标识",
        "forbidden_aliases": []
    },
    {
        "canonical": "gend",
        "aliases": ["gender", "sex", "gend"],
        "table": "fqz_fymx_test1",
        "desc": "性别代码：1=男，2=女",
        "forbidden_aliases": ["gender", "sex"]
    },
    {
        "canonical": "hilist_name",
        "aliases": ["item_name", "drug_name", "treat_name", "project_name", "fee_name", "hilist_name"],
        "table": "fqz_fymx_test1",
        "desc": "费用明细项目名称（药品/诊疗/耗材）",
        "forbidden_aliases": ["drug_name", "treat_name", "item_name"]
    },
    {
        "canonical": "hilist_code",
        "aliases": ["item_code", "drug_code", "treat_code", "list_code", "hilist_code"],
        "table": "fqz_fymx_test1",
        "desc": "医保标准项目编码",
        "forbidden_aliases": ["drug_code", "item_code"]
    },
    {
        "canonical": "det_item_fee_sumamt",
        "aliases": ["item_fee", "detail_amount", "item_amount", "det_item_fee_sumamt"],
        "table": "fqz_fymx_test1",
        "desc": "明细项目总金额",
        "forbidden_aliases": ["item_fee", "item_amount"]
    },
]

def seed_neo4j():
    print(f"Connecting to Neo4j at {uri}...")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            # Clear existing data
            print("Clearing existing Field nodes...")
            session.run("MATCH (n:Field) DETACH DELETE n")
            
            # Create nodes and relationships
            for entry in FIELD_ALIAS_REGISTRY:
                canonical = entry["canonical"].strip()
                print(f"Seeding field: {canonical}")
                
                # Create canonical node
                session.run(
                    "MERGE (f:Field {name: $name, is_canonical: true}) "
                    "SET f.table = $table, f.desc = $desc",
                    name=canonical, table=entry["table"], desc=entry["desc"]
                )
                
                # Create alias nodes and relationships
                for alias in entry["aliases"]:
                    alias = alias.strip()
                    session.run(
                        "MERGE (a:Field {name: $name, is_canonical: false}) "
                        "WITH a "
                        "MATCH (f:Field {name: $canonical}) "
                        "MERGE (a)-[:ALIAS_OF]->(f)",
                        name=alias, canonical=canonical
                    )
                
                # Create forbidden relationships
                for forbidden in entry["forbidden_aliases"]:
                    session.run(
                        "MATCH (f:Field {name: $name}) "
                        "SET f.is_forbidden = true",
                        name=forbidden
                    )
                    
        print("Neo4j seeding completed successfully!")
        driver.close()
    except Exception as e:
        print(f"Neo4j seeding failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    seed_neo4j()
