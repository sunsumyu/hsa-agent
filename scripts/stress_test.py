import requests
import json
import time

URL = "http://127.0.0.1:18081/ims-fqz/agent/chat"
LOG_FILE = "stress_test_results.log"

QUERIES = [
    "总结本月高风险案例",
    "总结1年内高风险案例",
    "总结2年内高风险案例",
    "总结本月高风险案例",
    "总结1年内高风险案例",
    "总结2年内高风险案例",
    "总结本月高风险案例",
    "总结1年内高风险案例",
    "总结2年内高风险案例",
    "总结本月高风险案例"
]

def log_result(round_num, query, result):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"--- 第 {round_num} 轮测试 ---\n")
        f.write(f"Query: {query}\n")
        f.write(f"Response: {result}\n")
        f.write("-" * 50 + "\n\n")

def run_test():
    print(f"=== 开始 10 轮压力测试 ===")
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== 医疗审计智能体 10 轮压力测试报告 ===\n\n")

    session_id = f"stress-test-{int(time.time())}"
    success_count = 0

    for i, q in enumerate(QUERIES):
        print(f"\r正在执行第 {i+1}/10 轮...", end="", flush=True)
        headers = {"X-Session-Id": session_id, "Content-Type": "application/json"}
        
        try:
            # 模拟真实前端发送字符串 body
            response = requests.post(URL, data=json.dumps(q), headers=headers, timeout=120)
            
            if response.status_code == 200:
                success_count += 1
                log_result(i+1, q, response.text)
            else:
                log_result(i+1, q, f"FAILED: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            log_result(i+1, q, f"ERROR: {str(e)}")
        
        time.sleep(2) # 轮次休息

    print(f"\n测试完成！成功率: {success_count}/10")
    print(f"详细对话记录已保存至: {LOG_FILE}")

if __name__ == "__main__":
    run_test()
