import re
import json

def main():
    log_file = "E:/chain/hsa-agent/logs/app_2026-06-14.log"
    time_pattern = re.compile(r"^2026-06-14 15:(3[5-9]|4[0-9]|5[0-5])")
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    current_case = "Unknown Case"
    
    case_tools = {}
    
    # We want to catch lines with Tool Calls and Results
    # Coder LLM Response line:
    # Coder LLM Response] Content: ... | Tool Calls: [...]
    # Results line:
    # 🔍 [Tool Execution Debug] Results: [...]
    
    for i, line in enumerate(lines):
        if not time_pattern.match(line):
            continue
            
        for case in ["QA-CUST-27", "QA-CUST-28", "QA-CUST-29", "QA-CUST-30", "QA-CUST-31"]:
            if case in line:
                current_case = case
                if current_case not in case_tools:
                    case_tools[current_case] = []
                break
                
        if "Tool Calls:" in line:
            # Extract tool calls
            idx = line.find("Tool Calls:")
            tool_calls_str = line[idx+11:].strip()
            try:
                # replacing single quotes with double quotes for json parse, or just eval
                # It's python list of dicts representation
                tool_calls = eval(tool_calls_str)
                for tc in tool_calls:
                    case_tools.setdefault(current_case, []).append({
                        "type": "call",
                        "name": tc.get("name"),
                        "args": tc.get("args"),
                        "id": tc.get("id"),
                        "time": line[:19]
                    })
            except Exception as e:
                # print(f"Error parsing tool call: {e} in line {line}")
                pass
                
        if "🔍 [Tool Execution Debug] Results:" in line:
            idx = line.find("Results:")
            results_str = line[idx+8:].strip()
            try:
                results_data = eval(results_str)
                # results_data is a list of tuples: (tool_call_dict, result_content)
                for tc, result in results_data:
                    # Find matching call in case_tools
                    for item in case_tools.get(current_case, []):
                        if item.get("type") == "call" and item.get("id") == tc.get("id"):
                            item["result"] = result
                            break
            except Exception as e:
                # print(f"Error parsing results: {e} in line {line}")
                pass

    # Print results
    for case, items in case_tools.items():
        print(f"\n==========================================")
        print(f"CASE: {case}")
        print(f"==========================================")
        for item in items:
            if item.get("type") == "call":
                print(f"[{item['time']}] Tool: {item['name']}")
                print(f"  Args: {item['args']}")
                if "result" in item:
                    res = str(item["result"])
                    # truncate result to 500 chars
                    if len(res) > 500:
                        res = res[:500] + "..."
                    print(f"  Result: {res}")
                print()

if __name__ == '__main__':
    main()
