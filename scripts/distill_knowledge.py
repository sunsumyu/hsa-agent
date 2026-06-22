import os
import re

LOG_DIR = r"e:\chain\hsa-agent\docs-log"

def distill():
    logs = [f for f in os.listdir(LOG_DIR) if f.startswith("log_")]
    summaries = []
    
    for log_file in logs:
        path = os.path.join(LOG_DIR, log_file)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 提取关键信息
        date_match = re.search(r"Date: (.*)", content)
        date = date_match.group(1) if date_match else "Unknown Date"
        
        # 寻找错误和修�?        errors = re.findall(r"ERROR.*", content)
        fixes = re.findall(r"(Fix|Refactor|Implement|Resolve).*", content)
        decisions = re.findall(r"(Decision|Policy|Shift).*", content)
        
        summaries.append({
            "file": log_file,
            "date": date,
            "errors": errors[:3],
            "actions": fixes[:3],
            "decisions": decisions[:3]
        })
        
    with open(r"e:\chain\hsa-agent\artifacts\distilled_history.json", "w", encoding="utf-8") as f:
        import json
        json.dump(summaries, f, indent=2, ensure_ascii=False)
    print(f"Distilled {len(summaries)} logs.")

if __name__ == "__main__":
    distill()

