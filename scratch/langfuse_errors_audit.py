import os
from langfuse import Langfuse
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json

# 1. 环境初始化
load_dotenv()

def audit_langfuse_errors():
    print("="*60)
    print(">>> [LANGFUSE DIAGNOSTIC] 正在启动链路深度分析...")
    print("="*60)

    # 2. 物理初始化 Client
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    
    if not pk or not sk:
        print("错误: 缺失 LANGFUSE 凭证，请检查 .env 文件。")
        return

    lf = Langfuse(public_key=pk, secret_key=sk, host=host)

    # 3. 抓取最近 24 小时的数据 (物理下钻)
    # 取最近 20 条 Trace 进行扫描
    try:
        print(f"📡 正在从 {host} 抓取最新链路记录...")
        traces = lf.api.traces.list(limit=20).data
        
        error_count = 0
        print(f"成功扫描到 {len(traces)} 条近期链路。正在识别故障指纹...\n")

        for trace in traces:
            # 这里的逻辑建议：识别 retry_count > 0 或 metadata 中包含 error 的链路
            # 获取该 Trace 的详细 Observations (包含各个 Node 的执行细节)
            trace_id = trace.id
            full_trace = lf.api.traces.get(trace_id)
            
            # 判断是否存在错误标志
            has_error = False
            error_msg = ""
            involved_sql = "N/A"
            node_name = "unknown"

            # 遍历 Trace 内部的所有 Observations (如 sqlexec 节点的报错)
            for obs in full_trace.observations:
                if obs.level == "ERROR":
                    has_error = True
                    error_msg = str(obs.status_message or obs.output)
                    # 尝试从输入中提炼 SQL
                    if obs.name == "sqlexec" or "SELECT" in str(obs.input).upper():
                        involved_sql = str(obs.input)[:200] + "..."
                        node_name = obs.name

            if has_error:
                error_count += 1
                print(f"[{error_count}] 发现故障链路!")
                print(f" - Trace ID: {trace_id}")
                print(f" - 故障节点: {node_name}")
                print(f" - 报错详情: {error_msg}")
                # 针对物理拦截器报错进行特殊解析
                if "物理审计拒绝" in error_msg:
                    print(" - [诊断结果] SQLGuardian AST 拦截触发：策略拦截成功，数据安全。")
                elif "Unknown function" in error_msg:
                    print(" - [诊断结果] 语义引擎失效：Agent 误用了 MySQL 语法。建议注入 ClickHouse 锦囊。")
                elif "Timeout" in error_msg or "30s" in error_msg:
                    print(" - [诊断结果] 算力熔断：查询代价过高，触发了驱动级 30s 保护。")
                
                print(f" - 涉案 SQL: {involved_sql}")
                print("-" * 40)

        if error_count == 0:
            print("🎉 恭喜！最近 20 条链路中未探测到显式错误特征。系统运行平稳。")
        else:
            print(f"✅ 诊断完成。共定位到 {error_count} 处物理冲突。")

    except Exception as e:
        print(f"诊断中断: {e}")

if __name__ == "__main__":
    audit_langfuse_errors()
