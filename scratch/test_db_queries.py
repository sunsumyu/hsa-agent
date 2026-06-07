import os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client
client = get_clickhouse_client()

print("All distinct hilist_name in default.fqz_fymx_test:")
print(client.query("SELECT DISTINCT hilist_name FROM default.fqz_fymx_test"))
