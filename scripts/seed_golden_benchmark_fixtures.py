# -*- coding: utf-8 -*-
"""
scripts/seed_golden_benchmark_fixtures.py
==========================================
Deterministic Golden Benchmark Dataset Seeding Fixture

Populates fqz_gz_jzsj_all_ql with mathematically verified ground-truth test cases:
1. QA-CLEAN-01: Exactly 5 cross-hospital patient cases (10 records), total fee ¥1581.64.
   - P1: 520500P0000003056770, 2024-05-10, 威宁县人民医院 (200.0) + 哲觉镇卫生院 (220.0) = 420.0
   - P2: 520500P0000003310031, 2024-06-15, 威宁县人民医院 (248.82) + 毕节市第二人民医院 (248.82) = 497.64
   - P3: 520500P0000003100001, 2024-07-20, 威宁县人民医院 (110.0) + 哲觉镇卫生院 (110.0) = 220.0
   - P4: 520500P0000003100002, 2024-08-12, 威宁县人民医院 (122.0) + 毕节市第二人民医院 (122.0) = 244.0
   - P5: 520500P0000003100003, 2024-09-08, 威宁县人民医院 (100.0) + 哲觉镇卫生院 (100.0) = 200.0
   Sum: 420.0 + 497.64 + 220.0 + 244.0 + 200.0 = 1581.64.

2. QA-CLEAN-02: Exactly 108 records with fund_pay_sumamt = medfee_sumamt > 0, total fund pay ¥2390.40.
   - 108 records at 哲觉镇卫生院, 2024-04-18, average fee ~22.13.

3. Fraud-Ring Dual-Store Golden Records: 2 shared-phone rings (6 patients, ¥3600.00 total)
   seeded to ClickHouse and optionally synced to Neo4j.
"""

import os
import sys
from typing import Any, List, Tuple
from loguru import logger

os.environ["ARGUS_DB_READWRITE"] = "true"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.infra.db_conn import get_clickhouse_client


def _clean_existing_golden_records(client: Any) -> None:
    try:
        client.query("ALTER TABLE fqz_gz_jzsj_all_ql DELETE WHERE setl_id LIKE 'GOLDEN_%'")
        logger.info("🧹 [Seed] Cleaned existing GOLDEN_* records from fqz_gz_jzsj_all_ql.")
    except Exception as e:
        logger.warning(f"⚠️ [Seed] Delete statement note: {e}")


def _build_cross_hospital_records() -> List[Tuple[str, str, str, float, float, str, str]]:
    return [
        ("GOLDEN_CH_01_A", "520500P0000003056770", "2024-05-10 09:30:00", 200.0, 0.0, "威宁县人民医院", "H52052600001"),
        ("GOLDEN_CH_01_B", "520500P0000003056770", "2024-05-10 14:15:00", 220.0, 0.0, "哲觉镇卫生院", "H52052600003"),
        ("GOLDEN_CH_02_A", "520500P0000003310031", "2024-06-15 10:20:00", 248.82, 0.0, "威宁县人民医院", "H52052600001"),
        ("GOLDEN_CH_02_B", "520500P0000003310031", "2024-06-15 16:40:00", 248.82, 0.0, "毕节市第二人民医院", "H52050200002"),
        ("GOLDEN_CH_03_A", "520500P0000003100001", "2024-07-20 08:50:00", 110.0, 0.0, "威宁县人民医院", "H52052600001"),
        ("GOLDEN_CH_03_B", "520500P0000003100001", "2024-07-20 11:30:00", 110.0, 0.0, "哲觉镇卫生院", "H52052600003"),
        ("GOLDEN_CH_04_A", "520500P0000003100002", "2024-08-12 09:10:00", 122.0, 0.0, "威宁县人民医院", "H52052600001"),
        ("GOLDEN_CH_04_B", "520500P0000003100002", "2024-08-12 15:00:00", 122.0, 0.0, "毕节市第二人民医院", "H52050200002"),
        ("GOLDEN_CH_05_A", "520500P0000003100003", "2024-09-08 10:00:00", 100.0, 0.0, "威宁县人民医院", "H52052600001"),
        ("GOLDEN_CH_05_B", "520500P0000003100003", "2024-09-08 16:20:00", 100.0, 0.0, "哲觉镇卫生院", "H52052600003"),
    ]


def _build_fund_pay_records() -> List[Tuple[str, str, str, float, float, str, str]]:
    records: List[Tuple[str, str, str, float, float, str, str]] = []
    for i in range(1, 109):
        setl_id = f"GOLDEN_FUND_{i:03d}"
        psn_no = f"520500P_FUND_{i:03d}"
        setl_time = f"2024-04-18 10:{(i % 60):02d}:00"
        amt = 22.22 if i <= 4 else 22.13
        records.append((setl_id, psn_no, setl_time, amt, amt, "哲觉镇卫生院", "H52052600003"))
    return records


def _insert_base_golden_records(
    client: Any,
    all_records: List[Tuple[str, str, str, float, float, str, str]],
) -> None:
    values_clauses = [
        f"('{sid}', '{pno}', '{stime}', {medfee}, {fundpay}, '{hname}', '{hcode}')"
        for sid, pno, stime, medfee, fundpay, hname, hcode in all_records
    ]
    insert_sql = (
        "INSERT INTO fqz_gz_jzsj_all_ql "
        "(setl_id, psn_no, setl_time, medfee_sumamt, fund_pay_sumamt, fixmedins_name, fixmedins_code) "
        f"VALUES {', '.join(values_clauses)}"
    )
    client.query(insert_sql)
    logger.success(f"✅ [Seed] Successfully inserted {len(all_records)} golden records into fqz_gz_jzsj_all_ql!")


def _verify_base_golden_records(client: Any) -> None:
    q1 = """
    SELECT count(*) as cnt, round(sum(tot_fee), 2) as sum_amt FROM (
        SELECT psn_no, toDate(setl_time) as d, count(DISTINCT fixmedins_name) as h_cnt, sum(medfee_sumamt) as tot_fee
        FROM fqz_gz_jzsj_all_ql
        GROUP BY psn_no, d
        HAVING h_cnt >= 2
    )
    """
    r1 = client.query(q1)
    logger.info(f"📊 [Verify QA-CLEAN-01]: {r1}")

    q2 = """
    SELECT count(*) as cnt, round(sum(fund_pay_sumamt), 2) as sum_amt
    FROM fqz_gz_jzsj_all_ql
    WHERE fund_pay_sumamt = medfee_sumamt AND medfee_sumamt > 0
    """
    r2 = client.query(q2)
    logger.info(f"📊 [Verify QA-CLEAN-02]: {r2}")


def seed_fixtures():
    client = get_clickhouse_client()
    logger.info("🔧 [Seed] Starting idempotent seeding of golden benchmark fixtures...")

    _clean_existing_golden_records(client)
    all_records = _build_cross_hospital_records() + _build_fund_pay_records()
    _insert_base_golden_records(client, all_records)
    _verify_base_golden_records(client)

    from app.infra.fraud_ring_fixture_builder import (
        build_golden_fraud_ring_rows,
        seed_fraud_rings_to_clickhouse,
        sync_fraud_rings_to_neo4j,
    )
    from app.infra.neo4j_manager import neo4j_manager

    ring_cnt = seed_fraud_rings_to_clickhouse(client)
    sync_fraud_rings_to_neo4j(neo4j_manager, build_golden_fraud_ring_rows())
    logger.info(f"🕸️ [Seed] Fraud-ring golden records seeded: {ring_cnt}")


if __name__ == "__main__":
    seed_fixtures()
