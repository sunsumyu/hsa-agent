# app/infra/fraud_ring_fixture_builder.py
from __future__ import annotations
from typing import Any, Dict, List
from loguru import logger


def build_golden_fraud_ring_rows() -> List[Dict[str, Any]]:
    """生成 2 组共享手机号欺诈环黄金基准数据（6 名参保人，严格合计 ¥3,600.00）。"""
    specs = [
        ("GOLDEN_RING_A1", "520500P_RING_A01", "13800009901", "威宁县人民医院", "H52052600001", 600.00),
        ("GOLDEN_RING_A2", "520500P_RING_A02", "13800009901", "威宁县人民医院", "H52052600001", 600.00),
        ("GOLDEN_RING_A3", "520500P_RING_A03", "13800009901", "哲觉镇卫生院", "H52052600003", 600.00),
        ("GOLDEN_RING_B1", "520500P_RING_B01", "13800009902", "毕节市第二人民医院", "H52050200002", 600.00),
        ("GOLDEN_RING_B2", "520500P_RING_B02", "13800009902", "毕节市第二人民医院", "H52050200002", 600.00),
        ("GOLDEN_RING_B3", "520500P_RING_B03", "13800009902", "威宁县人民医院", "H52052600001", 600.00),
    ]
    return [
        {
            "setl_id": sid,
            "psn_no": pno,
            "tel": tel,
            "setl_time": "2024-09-20 11:00:00",
            "medfee_sumamt": fee,
            "fund_pay_sumamt": round(fee * 0.85, 2),
            "fixmedins_name": hname,
            "fixmedins_code": hcode,
        }
        for sid, pno, tel, hname, hcode, fee in specs
    ]


def seed_fraud_rings_to_clickhouse(client: Any) -> int:
    """幂等写入欺诈环基准记录至 ClickHouse fqz_gz_jzsj_all_ql。"""
    rows = build_golden_fraud_ring_rows()
    client.query("ALTER TABLE fqz_gz_jzsj_all_ql DELETE WHERE setl_id LIKE 'GOLDEN_RING_%'")
    values_sql = ", ".join(
        f"('{r['setl_id']}', '{r['psn_no']}', '{r['tel']}', '{r['setl_time']}', "
        f"{r['medfee_sumamt']}, {r['fund_pay_sumamt']}, '{r['fixmedins_name']}', '{r['fixmedins_code']}')"
        for r in rows
    )
    insert_sql = (
        "INSERT INTO fqz_gz_jzsj_all_ql "
        "(setl_id, psn_no, tel, setl_time, medfee_sumamt, fund_pay_sumamt, fixmedins_name, fixmedins_code) "
        f"VALUES {values_sql}"
    )
    client.query(insert_sql)
    return len(rows)


def sync_fraud_rings_to_neo4j(neo4j_mgr: Any, rows: List[Dict[str, Any]]) -> bool:
    """将黄金欺诈环实体与关系同步至 Neo4j；若图库未启动则安全降级返回 False。"""
    cypher = (
        "UNWIND $rows AS row "
        "MERGE (p:Patient {psn_no: row.psn_no}) "
        "MERGE (h:Hospital {fixmedins_code: row.fixmedins_code}) "
        "SET h.name = row.fixmedins_name "
        "MERGE (t:Phone {tel: row.tel}) "
        "MERGE (p)-[v:VISITED]->(h) "
        "SET v.total_amt = row.medfee_sumamt, v.count = 1 "
        "MERGE (p)-[:HAS_PHONE]->(t)"
    )
    try:
        neo4j_mgr.execute_cypher(cypher, {"rows": rows})
        return True
    except Exception as exc:
        logger.warning(f"[FraudRingSeed] Neo4j 未就绪，跳过图端同步: {exc}")
        return False
