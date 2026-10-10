"""
app/core/tool_engine/grounder.py
================================
[V200.0] 确定性 AST 模式地面化接缝 (AST Schema Grounder)。
基于 sqlglot 在执行接缝前统一重写逻辑别名、中文表名和数据仓库别名至物理数据库真实表。
彻底消除因模型幻觉/历史习惯写出 dim_std_admdvs 等虚假表名导致的拦截失败。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple
import sqlglot
from sqlglot import exp
from loguru import logger

from app.core.registry.schema_registry import schema_registry


class SchemaGrounder:
    """
    确定性模式地面化器 (Deterministic Schema Grounder)。
    作为 ToolEngine 的内部实现组件，隐藏复杂的 AST 表名与列名映射规则。
    """

    # 预置高频逻辑表名/数仓维表到真实物理表的映射
    TABLE_ALIASES: Dict[str, str] = {
        # 行政区划字典
        "dim_std_admdvs": "fqz_admdvs",
        "dim_admdvs": "fqz_admdvs",
        "fqz_admdvs_dict": "fqz_admdvs",
        "admdvs_dict": "fqz_admdvs",
        "dict_admdvs": "fqz_admdvs",
        "dim_administrative_division": "fqz_admdvs",
        "administrative_division_code": "fqz_admdvs",
        "administrative_division": "fqz_admdvs",
        "dim_division": "fqz_admdvs",
        "行政区划表": "fqz_admdvs",
        "区划字典表": "fqz_admdvs",
        "区划字典": "fqz_admdvs",

        # 机构与药店名录
        "dim_hospital": "fqz_all_yy_yd",
        "dim_medins": "fqz_all_yy_yd",
        "fqz_all_yy_yd_1": "fqz_all_yy_yd",
        "定点医疗机构名录": "fqz_all_yy_yd",
        "医药机构名录": "fqz_all_yy_yd",
        "机构名录表": "fqz_all_yy_yd",

        # 结算主表与明细表
        "就诊结算表": "fqz_gz_jzsj_all_ql",
        "就诊表": "fqz_gz_jzsj_all_ql",
        "费用明细表": "fqz_fymx_test",
        "明细表": "fqz_fymx_test",
        "fymx_test": "fqz_fymx_test",

        # 药品与诊疗目录
        "药品目录表": "fqz_drug_mcs_info_list",
        "药品表": "fqz_drug_mcs_info_list",
        "dim_drug": "fqz_drug_mcs_info_list",
        "drug_catalog": "fqz_drug_mcs_info_list",
    }

    # 常见列名字段映射
    COLUMN_ALIASES: Dict[str, str] = {
        "单笔发生额": "det_item_fee_sumamt",
        "项目名称": "hilist_name",
        "药品名称": "hilist_name",
        "费用发生时间": "fee_ocur_time",
        "结算时间": "setl_time",
        "机构名称": "fixmedins_name",
        "medins_name": "fixmedins_name",
        "region_level": "admdvs_lv",
        "level_name": "admdvs_lv",
        "level_type": "admdvs_lv",
        "行政区划级别": "admdvs_lv",
        "行政区划代码": "admdvs",
        "行政区划名称": "admdvs_name",
    }

    @classmethod
    def ground_sql(cls, raw_sql: str) -> Tuple[str, List[str], List[str]]:
        """
        对 SQL 进行 AST 级模式地面化重写。

        Returns:
            rewritten_sql: 重写后的物理 ClickHouse SQL
            used_tables: 物理真实表名列表
            hints: 产生的诊断提示（若有）
        """
        if not raw_sql:
            return "", [], []

        clean = raw_sql.strip().rstrip(";； \n\r\t")

        # 1. 快速文本级中文别名预处理
        for k, v in cls.TABLE_ALIASES.items():
            if re.search(r'[\u4e00-\u9fa5]', k) and k in clean:
                clean = clean.replace(k, v)
        for k, v in cls.COLUMN_ALIASES.items():
            if re.search(r'[\u4e00-\u9fa5]', k):
                if k in clean:
                    clean = clean.replace(k, v)
            else:
                clean = re.sub(r'\b' + re.escape(k) + r'\b', v, clean, flags=re.IGNORECASE)

        # 2. AST 解析与别名替换
        try:
            tree = sqlglot.parse_one(clean, read="clickhouse")
        except Exception:
            # 若语法无法立即解析，返回原始 clean SQL
            return clean, [], []

        rewritten_count = 0
        used_tables: List[str] = []
        hints: List[str] = []

        # 收集 CTE 别名以避免误改
        cte_aliases = {
            cte.alias.lower()
            for cte in tree.find_all(exp.CTE)
            if cte.alias
        }

        # 遍历所有 Table 节点并执行确定性重写
        for table_node in tree.find_all(exp.Table):
            t_name = table_node.name.lower()
            if t_name in cte_aliases or t_name in {"dual"}:
                continue

            # 检查是否有注册的物理映射
            if t_name in cls.TABLE_ALIASES:
                target_real_table = cls.TABLE_ALIASES[t_name]
                logger.info(f"🔄 [SchemaGrounder] AST 表名地面化映射: `{table_node.name}` -> `{target_real_table}`")
                table_node.set("this", exp.to_identifier(target_real_table))
                used_tables.append(target_real_table)
                rewritten_count += 1
            else:
                used_tables.append(t_name)

        rewritten_sql = tree.sql(dialect="clickhouse")

        if rewritten_count > 0:
            hints.append(f"已自动将逻辑表名重写为底层物理表 (影响 {rewritten_count} 处)")

        return rewritten_sql, used_tables, hints

    @classmethod
    def get_registered_tables_hint(cls) -> str:
        """获取所有可用物理表及其中文业务场景，供反思智能体提供强提示。"""
        all_tables = schema_registry.get_all_table_names()
        if not all_tables:
            all_tables = ["fqz_gz_jzsj_all_ql", "fqz_fymx_test", "fqz_admdvs", "fqz_all_yy_yd", "fqz_drug_mcs_info_list"]
        return f"系统当前可用底层物理主表清单: {all_tables}"
