import re

def main():
    log_file = "E:/chain/hsa-agent/logs/app_2026-06-14.log"
    
    # We want to find logs between 15:35 and 15:55
    time_pattern = re.compile(r"^2026-06-14 15:(3[5-9]|4[0-9]|5[0-5])")
    
    # Let's read the log file. It might be UTF-8 or UTF-16 or GBK.
    encodings = ['utf-8', 'utf-16', 'gbk', 'utf-16-le', 'ansi']
    content = None
    for enc in encodings:
        try:
            with open(log_file, 'r', encoding=enc) as f:
                content = f.readlines()
            print(f"Successfully read log file with {enc}")
            break
        except Exception as e:
            continue
            
    if not content:
        print("Failed to read log file with any encoding.")
        return
        
    interesting_keywords = [
        "[语义层]", "[⚡ HYPER-FAST]", "[FieldKG]", "HyDE", "向量检索", 
        "Neo4j", "Graph", "query_fraud_ring", "Cypher", "lookup_medical_schema",
        "QA-CUST-27", "QA-CUST-28", "QA-CUST-29", "QA-CUST-30", "QA-CUST-31"
    ]
    
    current_case = "Unknown Case"
    results = []
    
    for line in content:
        # Check if line is within the time window
        if not time_pattern.match(line):
            continue
            
        # Track which case is running
        for case in ["QA-CUST-27", "QA-CUST-28", "QA-CUST-29", "QA-CUST-30", "QA-CUST-31"]:
            if case in line:
                current_case = case
                results.append(f"\n=== {current_case} ===")
                break
                
        # Check if the line contains any interesting keywords
        if any(kw in line for kw in interesting_keywords):
            results.append(f"{line.strip()}")
            
    print(f"Extracted {len(results)} lines.")
    with open("scratch/extracted_recall.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(results))

if __name__ == '__main__':
    main()
