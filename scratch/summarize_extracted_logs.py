import re

input_path = r"e:\chain\hsa-agent\scratch\extracted_bench_logs.txt"
output_path = r"e:\chain\hsa-agent\scratch\summarized_extracted_logs.txt"

with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

summary = []
current_case = ""

for line in lines:
    if "START LOGS FOR" in line:
        current_case = line.strip()
        summary.append(f"\n{current_case}\n" + "="*40 + "\n")
        continue
    
    # Clean up logs
    # Remove huge DB dumps
    if "'status': 'SUCCESS'" in line or "Results: [(" in line:
        # Just show the query/tool call name and argument SQL, not the huge data payload
        m_sql = re.search(r"'sql':\s*\"([^\"]+)\"", line) or re.search(r"'sql':\s*'([^']+)'", line)
        m_tool = re.search(r"'name':\s*'([^']+)'", line)
        if m_tool:
            tool_name = m_tool.group(1)
            sql_logic = m_sql.group(1) if m_sql else "N/A"
            # Simplify SQL printing
            sql_logic = sql_logic.replace('\\n', ' ').replace('\n', ' ')
            summary.append(f"  [Tool Call] {tool_name} (SQL: {sql_logic[:150]}...)")
        continue
        
    if "🔮 [Coder LLM Response] Content:" in line:
        content = line.split("Content:")[1].strip()
        # strip tool calls part if present
        if "| Tool Calls:" in content:
            content = content.split("| Tool Calls:")[0].strip()
        summary.append(f"  [Coder LLM Response] {content[:200]}...")
        continue
        
    if "🎯 [AlignerNode] 语义白盒漏斗对齐成功" in line:
        summary.append(f"  [AlignerNode] 对齐成功: {line.strip()[-30:]}")
        continue
        
    if "🤖 [LLMProvider] 正在调用模型:" in line:
        summary.append(f"  [LLMProvider] {line.strip()}")
        continue

    # Keep error logs
    if "ERROR" in line or "failed" in line.lower() or "exception" in line.lower() or " mised" in line.lower() or " hallucination" in line.lower():
        summary.append(f"  [ALERT/ERROR] {line.strip()[:300]}")
        continue

with open(output_path, 'w', encoding='utf-8') as out_f:
    out_f.write("\n".join(summary))

print(f"Summary written to {output_path}")
