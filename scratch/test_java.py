import requests

try:
    print("Testing Java backend on port 8081...")
    resp = requests.get("http://127.0.0.1:8081/task/person/list?searchValue=张三", timeout=5)
    print("Status Code:", resp.status_code)
    print("Response JSON:")
    print(resp.text)
except Exception as e:
    print("Failed on 8081:", e)

try:
    print("\nTesting Java backend on port 18081...")
    resp = requests.get("http://127.0.0.1:18081/task/person/list?searchValue=张三", timeout=5)
    print("Status Code:", resp.status_code)
    print("Response JSON:")
    print(resp.text)
except Exception as e:
    print("Failed on 18081:", e)
