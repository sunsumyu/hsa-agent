import os
import json
from datetime import datetime, timedelta

BRAIN_DIR = r"C:\Users\AREN\.gemini\antigravity\brain"
PROJECT_LOG_DIR = r"e:\chain\hsa-agent\docs-log"

def extract_logs():
    if not os.path.exists(PROJECT_LOG_DIR):
        os.makedirs(PROJECT_LOG_DIR)
        
    two_months_ago = datetime.now() - timedelta(days=60)
    
    conv_ids = [d for d in os.listdir(BRAIN_DIR) if os.path.isdir(os.path.join(BRAIN_DIR, d)) and d != "tempmediaStorage"]
    
    extracted_count = 0
    for cid in conv_ids:
        log_path = os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "overview.txt")
        if not os.path.exists(log_path):
            continue
            
        # 检查文件修改时�?        mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
        if mtime < two_months_ago:
            continue
            
        # 读取内容
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 简单的关键词过滤，确保是医�?HSA/Audit相关�?            if not any(k in content.lower() for k in ["hsa", "audit", "医保", "稽查", "sql", "clickhouse"]):
                continue
                
            # 保存到项目目�?            safe_date = mtime.strftime("%Y%m%d_%H%M%S")
            filename = f"log_{safe_date}_{cid[:8]}.md"
            save_path = os.path.join(PROJECT_LOG_DIR, filename)
            
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(f"# Conversation Log: {cid}\n")
                f.write(f"Date: {mtime.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(content)
            
            extracted_count += 1
            print(f"Extracted: {filename}")
        except Exception as e:
            print(f"Error processing {cid}: {e}")
            
    print(f"\nTotal extracted: {extracted_count}")

if __name__ == "__main__":
    extract_logs()

