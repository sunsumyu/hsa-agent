import json
try:
    with open(r'e:\chain\hsa-agent\app\endpoint_pools.json', 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    print("Successfully loaded JSON")
    print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")

