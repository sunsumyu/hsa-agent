"""
app/skills/federated_sideload_buffer.py
=======================================
[Matt Pocock Deep Module] 联邦侧载内存临时表生命周期与驱动适配器

核心职责：
1. 生成唯一的确定性侧载临时表名 (fqz_temp_sl_{batch_id})
2. 跨驱动统一批量写入：透明兼容 clickhouse-driver (execute) 与 clickhouse-connect (command + insert)
3. 异常弹性隔离：捕获 ClickHouse 物理写入错误，返回结构化错误元组与对齐的响应字典
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


class FederatedSideloadBuffer:
    """联邦侧载 ClickHouse 内存缓冲深模块"""

    def generate_temp_table_name(self, ids: List[str], prefix: str = "fqz_temp_sl_") -> str:
        """生成基于时间戳与实体指纹的唯一临时表名"""
        batch_id = hashlib.md5(f"{time.time()}_{len(ids)}".encode()).hexdigest()[:8]
        return f"{prefix}{batch_id}"

    def sideload_ids_to_clickhouse(
        self,
        ids: List[str],
        client: Any,
        prefix: str = "fqz_temp_sl_",
    ) -> Tuple[bool, str, Optional[str]]:
        """
        在 ClickHouse 中创建 Memory 引擎临时表并批量写入实体 ID 列表。
        返回: (is_success, temp_table_name, error_message)
        """
        if not ids:
            return False, "", "实体 ID 列表为空，无法进行侧载"

        temp_table = self.generate_temp_table_name(ids, prefix=prefix)
        create_sql = f"CREATE TABLE IF NOT EXISTS {temp_table} (id String) ENGINE = Memory"

        try:
            underlying = getattr(client, "client", client)
            if hasattr(underlying, "execute"):
                underlying.execute(create_sql)
                underlying.execute(f"INSERT INTO {temp_table} (id) VALUES", [(x,) for x in ids])
            elif hasattr(underlying, "command") and hasattr(underlying, "insert"):
                underlying.command(create_sql)
                underlying.insert(temp_table, [[x] for x in ids], column_names=["id"])
            else:
                raise AttributeError("ClickHouse 客户端实例缺少兼容的 execute 或 command/insert 接口")
            return True, temp_table, None
        except Exception as e:
            err_msg = str(e)
            logger.error(f"[FederatedSideloadBuffer] ClickHouse 写入临时表失败 ({temp_table}): {err_msg}")
            return False, temp_table, err_msg

    def format_sideload_response(self, temp_table: str, count: int) -> Dict[str, Any]:
        """格式化侧载成功后的标准响应报文"""
        return {
            "status": "SIDELOADED",
            "message": f"侧载成功！在 Neo4j 中发现了 {count} 个目标实体。",
            "temp_table": temp_table,
            "instruction": f"请立即编写 SQL，使用 INNER JOIN {temp_table} ON 主表的关键ID = {temp_table}.id 来关联查询明细及报销金额。",
        }


# 单例默认实例
federated_sideload_buffer = FederatedSideloadBuffer()
