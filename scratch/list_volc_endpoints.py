import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

def list_endpoints():
    ak = os.getenv("VOLC_ACCESS_KEY")
    sk = os.getenv("VOLC_SECRET_KEY")
    if not ak or not sk:
        print("Error: VOLC_ACCESS_KEY or VOLC_SECRET_KEY not set in environment.")
        return

    try:
        import volcenginesdkcore
        import volcenginesdkark
        
        print("Connecting to Volcengine...")
        configuration = volcenginesdkcore.Configuration()
        configuration.ak = ak
        configuration.sk = sk
        configuration.region = "cn-beijing"
        
        api_instance = volcenginesdkark.ARKApi(volcenginesdkcore.ApiClient(configuration))
        req = volcenginesdkark.ListEndpointsRequest()
        resp = api_instance.list_endpoints(req)
        
        if not resp.items:
            print("No endpoints found.")
            return
            
        print(f"Found {len(resp.items)} endpoints:")
        for item in resp.items:
            foundation_model = "unknown"
            if hasattr(item, 'model_reference') and item.model_reference:
                ref = item.model_reference
                if hasattr(ref, 'foundation_model') and ref.foundation_model:
                    fm = ref.foundation_model
                    if isinstance(fm, dict):
                        foundation_model = fm.get('name', 'unknown')
                    elif hasattr(fm, 'name'):
                        foundation_model = fm.name
            
            name = item.name
            try:
                if isinstance(name, str):
                    name = name.encode('latin1').decode('utf-8')
            except Exception:
                pass
            
            print(f"- ID: {item.id}")
            print(f"  Name: {name}")
            print(f"  Foundation Model: {foundation_model}")
            print(f"  Status: {getattr(item, 'status', 'unknown')}")
            print(f"  Description: {getattr(item, 'description', '')}")
            print()
            
    except Exception as e:
        print(f"Error listing endpoints: {e}")

if __name__ == "__main__":
    list_endpoints()
