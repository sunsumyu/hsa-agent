"""
基线计算服务 - 自动执行 Phase 1 分位数查询

解决问题：
- Phase 1 基线计算未自动化执行
- 基线计算结果未注入 Phase 2 SQL
- 基线计算失败时无降级策略
- 缺乏基线计算的可观测性
"""
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class BaselineResult:
    """基线计算结果"""
    baseline_value: float  # 基线值
    quantile: float  # 使用的分位数
    sample_count: int  # 样本数量
    time_range: Optional[Tuple[str, str]]  # 数据时间范围
    success: bool  # 是否成功
    error_message: Optional[str]  # 错误信息
    is_fallback: bool = False  # 是否使用了降级值


class BaselineCalculator:
    """自动执行 Phase 1 基线计算

    使用流程：
    1. 接收阈值决策引擎的 baseline_sql
    2. 自动执行 ClickHouse 查询
    3. 应用安全边界
    4. 返回基线结果
    5. 失败时使用降级策略
    """

    @classmethod
    def execute(
        cls,
        baseline_sql: str,
        safety_bounds: Dict[str, float],
        fallback_threshold: float,
        client: Any = None
    ) -> BaselineResult:
        """执行基线计算

        Args:
            baseline_sql: Phase 1 基线 SQL
            safety_bounds: 安全边界 {min, max}
            fallback_threshold: 降级默认阈值
            client: 可选的 ClickHouse 客户端

        Returns:
            BaselineResult: 基线计算结果
        """
        if not baseline_sql:
            logger.warning("⚠️ [BaselineCalculator] 无基线SQL，使用降级阈值")
            return BaselineResult(
                baseline_value=fallback_threshold,
                quantile=0.95,
                sample_count=0,
                time_range=None,
                success=False,
                error_message="无基线SQL",
                is_fallback=True
            )

        logger.info(f"📊 [BaselineCalculator] 执行 Phase 1 基线查询: {baseline_sql}")

        try:
            if client is None:
                from app.infra.db_conn import get_clickhouse_client
                client = get_clickhouse_client()

            # 执行基线查询
            result_rows = cls._execute_query(client, baseline_sql)

            if not result_rows or not result_rows[0] or result_rows[0][0] is None:
                raise ValueError("基线查询返回空结果")

            baseline_value = float(result_rows[0][0])

            # 应用安全边界
            min_t = safety_bounds.get("min", 0)
            max_t = safety_bounds.get("max", float("inf"))
            original_value = baseline_value
            baseline_value = max(min_t, min(max_t, baseline_value))

            if baseline_value != original_value:
                logger.warning(
                    f"⚠️ [BaselineCalculator] 基线值被安全边界调整: "
                    f"{original_value} -> {baseline_value} "
                    f"(边界: [{min_t}, {max_t}])"
                )

            # 获取样本数量（辅助信息）
            sample_count = cls._get_sample_count(client, baseline_sql)

            # 获取时间范围（辅助信息）
            time_range = cls._get_time_range(client, baseline_sql)

            logger.success(
                f"✅ [BaselineCalculator] 基线计算成功: "
                f"baseline={baseline_value}元, "
                f"samples={sample_count}, "
                f"time_range={time_range}"
            )

            return BaselineResult(
                baseline_value=baseline_value,
                quantile=cls._extract_quantile_from_sql(baseline_sql),
                sample_count=sample_count,
                time_range=time_range,
                success=True,
                error_message=None,
                is_fallback=False
            )

        except Exception as e:
            logger.error(f"❌ [BaselineCalculator] 基线计算失败: {e}")

            # 降级策略：使用配置默认值
            logger.warning(
                f"⚠️ [BaselineCalculator] 降级使用默认阈值: {fallback_threshold}元"
            )

            return BaselineResult(
                baseline_value=fallback_threshold,
                quantile=0.95,
                sample_count=0,
                time_range=None,
                success=False,
                error_message=str(e),
                is_fallback=True
            )

    @classmethod
    def _execute_query(cls, client: Any, sql: str) -> list:
        """执行 ClickHouse 查询"""
        if hasattr(client, 'client'):
            inner = client.client
            if hasattr(inner, 'execute'):
                return inner.execute(sql)
            elif hasattr(inner, 'query'):
                return inner.query(sql).result_rows
        elif hasattr(client, 'execute'):
            return client.execute(sql)
        elif hasattr(client, 'query'):
            return client.query(sql).result_rows
        else:
            raise ValueError("无法识别的 ClickHouse 客户端类型")

    @classmethod
    def _get_sample_count(cls, client: Any, baseline_sql: str) -> int:
        """获取样本数量"""
        try:
            # 从基线 SQL 中提取表名
            table = cls._extract_table_from_sql(baseline_sql)
            if not table:
                return 0

            count_sql = f"SELECT count() FROM {table}"

            # 提取 WHERE 条件
            if "WHERE" in baseline_sql.upper():
                where_part = baseline_sql.upper().split("WHERE")[1].strip()
                # 移除可能的子查询
                if not any(kw in where_part for kw in ["SELECT", "FROM"]):
                    count_sql += f" WHERE {where_part}"

            result = cls._execute_query(client, count_sql)
            return int(result[0][0]) if result and result[0] else 0

        except Exception as e:
            logger.debug(f"📊 [BaselineCalculator] 样本数量获取失败: {e}")
            return 0

    @classmethod
    def _get_time_range(cls, client: Any, baseline_sql: str) -> Optional[Tuple[str, str]]:
        """获取数据时间范围"""
        try:
            table = cls._extract_table_from_sql(baseline_sql)
            if not table:
                return None

            time_sql = f"SELECT min(setl_time), max(setl_time) FROM {table}"
            result = cls._execute_query(client, time_sql)

            if result and result[0] and result[0][0] and result[0][1]:
                return (str(result[0][0]), str(result[0][1]))

        except Exception as e:
            logger.debug(f"📊 [BaselineCalculator] 时间范围获取失败: {e}")

        return None

    @classmethod
    def _extract_table_from_sql(cls, sql: str) -> Optional[str]:
        """从 SQL 中提取表名"""
        import re
        match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
        return match.group(1) if match else None

    @classmethod
    def _extract_quantile_from_sql(cls, sql: str) -> float:
        """从 SQL 中提取分位数"""
        import re
        match = re.search(r'quantile\((\d+\.?\d*)\)', sql, re.IGNORECASE)
        return float(match.group(1)) if match else 0.95


# 便捷函数
def calculate_baseline(
    baseline_sql: str,
    safety_bounds: Dict[str, float],
    fallback_threshold: float = 500
) -> BaselineResult:
    """计算基线的便捷函数"""
    return BaselineCalculator.execute(baseline_sql, safety_bounds, fallback_threshold)
