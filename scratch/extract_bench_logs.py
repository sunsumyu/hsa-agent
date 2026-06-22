import os

log_path = r"e:\chain\hsa-agent\logs\app_2026-06-05.log"
output_path = r"e:\chain\hsa-agent\scratch\extracted_bench_logs.txt"

cids = ["QA-CUST-23", "QA-CUST-24", "QA-CUST-25", "QA-CUST-26"]
lines_to_keep = []

if os.path.exists(log_path):
    print(f"Reading logs from {log_path}...")
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        in_case = False
        current_case = ""
        context_lines = []
        for line in f:
            # Check if line indicates starting a case
            # E.g. search for BENCH_QA-CUST-
            found_cid = None
            for cid in cids:
                if cid in line:
                    found_cid = cid
                    break
            
            if found_cid:
                in_case = True
                current_case = found_cid
                # Write a separator in context
                context_lines.append(f"\n=================== START LOGS FOR {current_case} ===================\n")
            
            # If in_case, check if we hit next case or if we just want to collect relevant logs
            # Let's collect lines containing Coder, Planner, Aligner, Reporter, Coder LLM Response, SQL_EXECUTION, etc.
            # Or simply collect all log lines containing keywords, or just everything when in_case is True.
            # To avoid huge file size, let's keep lines with case ID, session ID, or key agent milestones:
            keep = False
            if in_case:
                # Keep lines with important milestones
                milestones = ["[SmartRouter]", "智能体", "AlignerNode", "PLANNER", "ALIGNER", "SQLEXEC", "REPORTER", "CONSOLIDATOR", "Coder LLM Response", "Tool Execution Debug", "sql_logic", "methodology", "data:", "ERROR", "Warning", "failed"]
                if any(m in line for m in milestones) or current_case in line or "BENCH_" in line:
                    keep = True
                    
            if keep:
                context_lines.append(line.strip())
                
    with open(output_path, 'w', encoding='utf-8') as out_f:
        out_f.write("\n".join(context_lines))
    print(f"Extracted logs written to {output_path} ({len(context_lines)} lines)")
else:
    print(f"Log path does not exist: {log_path}")
