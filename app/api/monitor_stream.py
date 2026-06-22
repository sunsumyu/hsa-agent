import os
import sys
import json
import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Sequence, Union
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
if os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = os.getenv("HF_HOME")  # 保留环境变量, 但不硬编码路径

from app.core.agent_graph import get_graph_executor

class AuditStreamProcessor:
    """[V48.0] 生产级审计监控流处理器"""
    
    def __init__(self, queue_file: str = "data/audit_queue.json"):
        self.queue_file = queue_file
        self.results_file = "data/production_audit_alerts.json"
        os.makedirs("data", exist_ok=True)
        
    async def process_event(self, event: Dict):
        """处理单个审计事件"""
        event_id = event.get("event_id", "unknown")
        logger.info(f"🚀 [STREAM] 正在处理审计事件: {event_id}")
        
        # 构建 Agent 输入
        image_path = event.get("evidence_image")
        user_input = (
            f"系统自动触发：检测到患者 {event.get('patient_name')} 在 {event.get('hosp_name')} 的高额结算。 "
            f"请对比附件单据 ({image_path}) 与结算明细，核查虚增药品风险。"
        )
        
        inputs = {"messages": [("user", user_input)]}
        config = {"configurable": {"thread_id": f"stream_{event_id}"}}
        
        try:
            # 执行异步审计图谱
            agent, _ = get_graph_executor()
            final_state = await agent.ainvoke(inputs, config=config)
            
            # 提取最终报告
            report_msg = final_state["messages"][-1].content
            
            # 模拟告警触发逻辑：如果涉及金额 > 0 且包含违规关键词
            if "违规" in report_msg or "发现" in report_msg:
                self._trigger_alert(event_id, report_msg)
                
        except Exception as e:
            logger.error(f"❌ 事件 {event_id} 处理崩溃: {e}")

    def _trigger_alert(self, event_id: str, report: str):
        """模拟生产告警推送 (Webhook/Email)"""
        alert_data = {
            "timestamp": datetime.now().isoformat(),
            "event_id": event_id,
            "level": "CRITICAL",
            "summary": report[:200],
            "full_report_path": f"data/reports/{event_id}.md"
        }
        
        # 写入告警日志
        with open(self.results_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert_data, ensure_ascii=False) + "\n")
            
        logger.warning(f"🚨 [ALERT] 发现重大违规嫌疑！事件 ID: {event_id}。告警已推送到风控中心。")

    async def run_forever(self):
        """持续监听循环 (模拟消息队列)"""
        logger.info("📡 穿透审计监控流已启动，正在监听事件队列...")
        
        while True:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    try:
                        events = json.load(f)
                    except (json.JSONDecodeError, ValueError):
                        events = []
                
                if events:
                    # 并发处理当前队列中的所有事件
                    tasks = [self.process_event(ev) for ev in events]
                    await asyncio.gather(*tasks)
                    
                    # 处理完后清空模拟队列
                    os.remove(self.queue_file)
            
            await asyncio.sleep(5)  # 每 5 秒轮询一次

if __name__ == "__main__":
    processor = AuditStreamProcessor()
    asyncio.run(processor.run_forever())
