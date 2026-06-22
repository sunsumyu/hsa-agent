import json
import os

def search_scope():
    path = r"C:\Users\AREN\AppData\Roaming\Codex\web\Codex\sentry\scope_v3.json"
    if not os.path.exists(path):
        print("Sentry scope file not found")
        return
        
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)
        
    scope = data.get('scope', {})
    breadcrumbs = scope.get('breadcrumbs', [])
    print(f"Total breadcrumbs: {len(breadcrumbs)}")
    
    keywords = ['window', 'fullscreen', 'bounds', 'display', 'screen', 'gpu', 'maximized', 'maximize', 'crash', 'fail', 'error', 'trans', 'transparent', 'unresponsive', 'render-process-gone']
    
    matching_crumbs = []
    for crumb in breadcrumbs:
        message = crumb.get('message', '')
        data_field = str(crumb.get('data', ''))
        category = crumb.get('category', '')
        
        text = f"{message} {data_field} {category}".lower()
        if any(kw in text for kw in keywords):
            matching_crumbs.append(crumb)
            
    print(f"Found {len(matching_crumbs)} matching breadcrumbs:")
    for crumb in matching_crumbs[:50]:
        print(json.dumps(crumb, indent=2))

if __name__ == "__main__":
    search_scope()
