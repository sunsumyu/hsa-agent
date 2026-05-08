import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

host = os.getenv('CLICKHOUSE_HOST', '121.196.219.211')
port = int(os.getenv('CLICKHOUSE_PORT', '8123'))
user = os.getenv('CLICKHOUSE_USER', 'default')
passwd = os.getenv('CLICKHOUSE_PASSWORD', '')

client = clickhouse_connect.get_client(host=host, port=port, username=user, password=passwd)
result = client.query("DESCRIBE TABLE default.fqz_gz_jzsj_all_ql")
print("Table structure:")
for row in result.result_rows:
    print(row)
