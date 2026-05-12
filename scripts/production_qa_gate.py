import os
import sys
import asyncio
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
# HF_HOME: use .env or system default

from app.agent_graph import get_graph_executor
from app.security import SQLGuardian
from app.semantic_memory import cognitive_memory_manager

class HSAProductionQA:
    """[V50.0] HSA 生产环境 CI/CD 质检闸门"""
    
    def __init__(self):
        self.executor, _ = get_graph_executor()
        self.results = {"functional": False, "safety": False, "visual": False}
        self.test_session = "ci_test_session_v50"

    async def check_functional_regression(self):
        """1. 回归测试：验证核心审计逻辑"""
        logger.info("🧪 [QA] 正在执行核心审计功能回归测试...")
        user_input = "帮我查查 P001 在 2024-05-01 的重复收费情况。"
        inputs = {"messages": [("user", user_input)], "session_id": self.test_session}
        config = {"configurable": {"thread_id": self.test_session}}
        
        try:
            final_state = await self.executor.ainvoke(inputs, config=config)
            report = final_state.get("structured_report")
            if report and report.total_amount > 0:
                logger.success("✅ 功能回归测试通过：成功捕获预设违规。")
                self.results["functional"] = True
            else:
                logger.error("❌ 功能回归测试失败：未产出预期的审计结论。")
        except Exception as e:
            logger.error(f"❌ 功能回归崩溃: {e}")

    def check_safety_guard(self):
        """2. 安全围栏测试：验证恶意 SQL 拦截"""
        logger.info("🧪 [QA] 正在验证 SQLGuardian 安全围栏...")
        malicious_sql = "DROP TABLE fqz_gz_jzsj_all_ql;"
        try:
            SQLGuardian.validate_sql(malicious_sql)
            logger.error("❌ 安全测试失败：SQLGuardian 未能拦截 DROP 命令！")
        except Exception:
            logger.success("✅ 安全测试通过：SQLGuardian 成功拦截了危险指令。")
            self.results["safety"] = True

    def check_visual_integrity(self):
        """3. 视觉一致性测试：验证 HTML 仪表盘生成"""
        logger.info("🧪 [QA] 正在验证可视化仪表盘生成...")
        html_path = f"data/reports/dashboard_{self.test_session}.html"
        if os.path.exists(html_path):
            logger.success("✅ 视觉质检通过：富媒体审计仪表盘已就绪。")
            self.results["visual"] = True
        else:
            logger.error("❌ 视觉质检失败：未发现生成的 HTML 报告。")

    async def run_gate(self):
        logger.info("=== 🚀 HSA 生产环境 CI/CD 自动化质检开始 ===")
        
        # 0. 经验灌输：确保智能体具备识别违规的知识
        logger.info("🧪 [QA] 正在进行前置知识灌输...")
        exp = "审计经验：同一天内针对同一患者 psn_no 有多次结算记录即判定为重复收费。"
        cognitive_memory_manager.add_audit_event(exp, importance=1.0, topic="重复收费审计")
        
        # 1. 执行质检项
        await self.check_functional_regression()
        self.check_safety_guard()
        self.check_visual_integrity()
        
        # 判定是否通过
        passed = all(self.results.values())
        if passed:
            logger.success("🏆 [PASS] 所有质检项已通过！代码可安全合并至生产分支。")
            sys.exit(0)
        else:
            logger.critical("🚨 [FAIL] 质检未通过！请修复上述问题后再重试。")
            sys.exit(1)

if __name__ == "__main__":
    qa = HSAProductionQA()
    asyncio.run(qa.run_gate())
