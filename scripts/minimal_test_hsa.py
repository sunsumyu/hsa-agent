import os
import sys
import json
import asyncio
from loguru import logger

# 增加路径
sys.path.append(os.getcwd())

# Mock DB client
class MockResult:
    def __init__(self, rows, names):
        self.result_rows = rows
        self.column_names = names

class MockClient:
    def query(self, sql):
        if "医保稽核" in sql:
            return MockResult([('医保稽核',)], ['test_str'])
        return MockResult([], [])

from app.infra.db_conn import CharsetProxy

async def test_charset_proxy():
    logger.info("🧪 测试 1: Charset Proxy Logic")
    mock_raw_client = MockClient()
    proxy = CharsetProxy(mock_raw_client)
    res = proxy.query("SELECT '医保稽核' AS test_str")
    logger.success(f"Proxy 返回数据: {res.result_rows}")
    assert res.result_rows[0][0] == '医保稽核'

def test_semantic_router():
    logger.info("🧪 测试 2: Semantic Router (Avoidance Guide)")
    from app.skills.semantic_layer import MetadataMappingLayer
    mapper = MetadataMappingLayer()
    guide = mapper.detect("我想查询重复住院的职工医保人员")
    logger.info(f"生成指南:\n{guide}")
    assert "职工" in guide
    assert "重复" in guide

def test_sql_linter():
    logger.info("🧪 测试 3: SQL Agentic Linter")
    from app.skills.sql_validator import sql_validator
    bad_sql = "SELECT count(*) FROM fqz_table GROUP BY setl_id"
    ok, msg = sql_validator.agentic_linter(bad_sql)
    logger.info(f"Linter 拦截结果: {ok}, 消息: {msg}")
    assert ok is False
    assert "SETL_ID" in msg.upper()

    good_sql = "SELECT count(*) FROM fqz_table GROUP BY psn_no"
    ok, msg = sql_validator.agentic_linter(good_sql)
    assert ok is True

def test_sequence_validator():
    logger.info("🧪 测试 4: Sequence Validator")
    from app.core.agent_graph import SequenceValidator
    state_bad = {
        "methodology": "Phase 1: Graph 分析发现团伙",
        "execution_trace": ["SQL 执行成功"]
    }
    ok, msg = SequenceValidator.validate_step(state_bad)
    logger.info(f"Sequence 校验结果: {ok}, 消息: {msg}")
    assert ok is False
    assert "图谱" in msg

def test_anomaly_data():
    logger.info("🧪 测试 5: Anomalous Data Warning")
    from app.core.booster import booster
    bad_data = [
        {"psn_no": "A1", "medfee": 14848},
        {"psn_no": "A2", "medfee": 14848},
        {"psn_no": "A3", "medfee": 14848},
        {"psn_no": "A4", "medfee": 14848},
        {"psn_no": "A5", "medfee": 14848}
    ]
    msg = booster.detect_anomalous_consistency(bad_data)
    logger.info(f"异常数值探测: {msg}")
    assert msg is not None
    assert "14848" in msg

async def test_medical_code_tool():
    logger.info("🧪 测试 6: Medical Code Tool")
    from app.tools import expand_medical_codes
    # expand_medical_codes is a structured tool
    res = expand_medical_codes.func("妇科")
    logger.info(f"编码扩展结果:\n{res}")
    assert "O00" in res

async def main():
    logger.info("🚀 开始 HSA Agent 最小化逻辑测试")
    await test_charset_proxy()
    test_semantic_router()
    test_sql_linter()
    test_sequence_validator()
    test_anomaly_data()
    await test_medical_code_tool()
    logger.success("✨ 所有核心组件逻辑测试通过！")

if __name__ == "__main__":
    asyncio.run(main())
