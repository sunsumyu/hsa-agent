import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.core.quota.volcengine import VolcengineQuotaFetcher

def list_all():
    fetcher = VolcengineQuotaFetcher()
    import volcenginesdkcore
    import volcenginesdkbilling

    # Ensure env vars are set
    os.environ["VOLCENGINE_ACCESS_KEY"] = fetcher.ak
    os.environ["VOLCENGINE_SECRET_KEY"] = fetcher.sk

    configuration = volcenginesdkcore.Configuration()
    configuration.region = "cn-beijing"
    
    try:
        api_instance = volcenginesdkbilling.BILLINGApi(volcenginesdkcore.ApiClient(configuration))
        packages = []
        next_token = None
        
        while True:
            req = volcenginesdkbilling.ListResourcePackagesRequest(
                resource_type='Package',
                status='Effective', 
                max_results='20',
                next_token=next_token
            )
            resp = api_instance.list_resource_packages(req)
            pkgs = getattr(resp, 'list', [])
            if pkgs:
                packages.extend(pkgs)
            
            next_token = getattr(resp, 'next_token', None)
            if not next_token or next_token == '0' or next_token == '':
                break
    except Exception as e:
        print("API exception:", e)
        return

    print(f"Total packages retrieved: {len(packages)}")
    for i, pkg in enumerate(packages):
        name = getattr(pkg, 'configuration_name', '')
        code = getattr(pkg, 'configuration_code', '')
        prod = getattr(pkg, 'product', '')
        prod_name = getattr(pkg, 'product_name', '')
        avail = getattr(pkg, 'available_amount', '0')
        total = getattr(pkg, 'total_amount', '0')
        status = getattr(pkg, 'status', '')
        
        # print first few or matches
        print(f"[{i}] Name: {name} | Code: {code} | Prod: {prod} | ProdName: {prod_name} | Avail: {avail} / {total} | Status: {status}")

if __name__ == '__main__':
    list_all()
