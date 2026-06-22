import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

def list_endpoints_by_region(region):
    ak = os.getenv("VOLC_ACCESS_KEY")
    sk = os.getenv("VOLC_SECRET_KEY")
    if not ak or not sk:
        print("Error: VOLC_ACCESS_KEY or VOLC_SECRET_KEY not set in environment.")
        return []

    try:
        import volcenginesdkcore
        import volcenginesdkark
        
        configuration = volcenginesdkcore.Configuration()
        configuration.ak = ak
        configuration.sk = sk
        configuration.region = region
        
        api_instance = volcenginesdkark.ARKApi(volcenginesdkcore.ApiClient(configuration))
        req = volcenginesdkark.ListEndpointsRequest()
        resp = api_instance.list_endpoints(req)
        
        return resp.items or []
    except Exception as e:
        print(f"Error listing endpoints in {region}: {e}")
        return []

def test_endpoints():
    regions = ["cn-beijing", "cn-shanghai", "cn-guangzhou"]
    all_endpoints = []
    for r in regions:
        print(f"Checking region: {r}...")
        eps = list_endpoints_by_region(r)
        for ep in eps:
            all_endpoints.append((r, ep))
            
    print(f"\nFound total {len(all_endpoints)} endpoints across regions:")
    
    from langchain_core.messages import HumanMessage
    from app.infra.model_manager import model_manager
    
    for region, ep in all_endpoints:
        foundation_model = "unknown"
        if hasattr(ep, 'model_reference') and ep.model_reference:
            ref = ep.model_reference
            if hasattr(ref, 'foundation_model') and ref.foundation_model:
                fm = ref.foundation_model
                if isinstance(fm, dict):
                    foundation_model = fm.get('name', 'unknown')
                elif hasattr(fm, 'name'):
                    foundation_model = fm.name
                    
        name = ep.name
        try:
            if isinstance(name, str):
                name = name.encode('latin1').decode('utf-8')
        except Exception:
            pass

        print(f"\n- ID: {ep.id} in region {region}")
        print(f"  Name: {name}")
        print(f"  Foundation Model: {foundation_model}")
        print(f"  Status: {getattr(ep, 'status', 'unknown')}")
        
        # Test call
        print("  Testing invocation...")
        api_key = os.getenv("VOLC_API_KEY")
        base_url = os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        
        # Adjust base url for other regions if needed, though cn-beijing endpoint usually works for all regions or we construct regional url
        # Volcengine regional base url format: https://ark.{region}.volces.com/api/v3
        regional_base_url = f"https://ark.{region}.volces.com/api/v3"
        
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=ep.id,
                openai_api_key=api_key,
                openai_api_base=regional_base_url,
                temperature=0.0,
                timeout=10.0,
                max_retries=0
            )
            resp = llm.invoke([HumanMessage(content="1+1=?")])
            print(f"  ✅ SUCCESS! Response: {resp.content.strip()}")
        except Exception as e:
            print(f"  ❌ FAILED! Error: {e}")

if __name__ == "__main__":
    test_endpoints()
