"""
app/schema_injector.py
======================
[企业级可复用模块] 精准 Schema 注入工具 (V90.5)

核心改进：
    V80.0 -> V90.5 升级要点：
    1. 问题分类 & 表路由：根据用户问题识别数据域，定位目标表
    2. 全量 DDL 分区注入：注入目标表的**全部字段**（而非 top-k 片段），
       从根本上消除字段幻觉
    3. 分层提示：按数据域分层描述表的用途与约束

设计理念：
    资料分区分层 -> 查得快、查得准、不幻觉。
    - 分区：每张物理表分属不同数据域，不混淆。
    - 分层：核心字段（必用）+ 辅助字段（可选）+ 约束（禁忌）
"""

from __future__ import annotations
import os
import re
from typing import List, Dict, Optional, Tuple, Set
from loguru import logger
from app.schema_manager import schema_manager


# ── 数据域定义：问题分类 & 表路由映射 ──────────────────────────────────────────
# 每个域包含：触发关键词、目标表、数据域描述

_DATA_DOMAINS = [
    {
        "domain": "settlement",
        "desc": "结算/住院/门诊/报销/患者个人明细",
        "tables": ["FQZ_GZ_JZSJ_ALL_QL"],
        "keywords": [
            "结算", "住院", "门诊", "报销", "费用", "金额", "患者", "参保",
            "重复", "分解", "挂床", "冒名", "套保", "骗保",
            "性别", "诊断", "手术", "科室", "天数", "床位",
            "setl", "psn", "mdtrt", "medfee", "fund_pay",
            "入院", "出院", "再入院", "短期", "转院",
            "异常", "审计", "稽核", "核查", "违规",
            "P99", "psn_no",
        ],
    },
    {
        "domain": "hospital_monthly",
        "desc": "医疗机构月度汇总统计",
        "tables": ["FQZ_ALL_YY_YD_1"],
        "keywords": [
            "医院", "机构", "月度", "汇总", "统计", "排名",
            "变异", "VIX", "离群", "偏高", "偏低",
            "医院对比", "机构对比", "总额",
            "fixmedins",
        ],
    },
    {
        "domain": "drug_catalog",
        "desc": "药品/诊疗项目/耗材目录",
        "tables": ["FQZ_DRUG_MCS_INFO_LIST"],
        "keywords": [
            "药品", "药物", "处方", "用药", "购药",
            "目录", "耗材", "诊疗项目", "医保目录",
            "drug", "med_list", "hilist",
        ],
    },
]

# 默认兜底：如果没有任何域匹配，注入主表
_DEFAULT_TABLES = ["FQZ_GZ_JZSJ_ALL_QL"]


class SchemaInjector:
    """
    [V90.5] 分区分层 Schema 注入器。
    Pipeline:
        1. classify(question) -> 识别数据域 -> 确定目标表
        2. inject(question)   -> 对目标表注入全量 DDL + 分层约束
    """

    def __init__(self, external_schema_file: Optional[str] = None):
        self._external_file = external_schema_file
        self._extended_seeds: Optional[List[Dict]] = None

    # ── 问题分类：识别数据域 ──────────────────────────────────────────────────────────

    def classify(self, user_question: str) -> List[Dict]:
        """
        根据用户问题识别涉及的数据域。
        Returns:
            匹配的域列表，按相关度降序，每项含 domain/desc/tables/score
        """
        if not user_question or not user_question.strip():
            return [_DATA_DOMAINS[0]]  # 默认主表

        text = user_question.lower()
        scored = []
        for domain in _DATA_DOMAINS:
            score = sum(1 for kw in domain["keywords"] if kw.lower() in text)
            if score > 0:
                scored.append({**domain, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)

        if not scored:
            return [_DATA_DOMAINS[0]]  # 兜底主表

        return scored

    def get_target_tables(self, user_question: str) -> List[str]:
        """返回目标表名列表（去重、有序）"""
        domains = self.classify(user_question)
        tables = []
        seen = set()
        for d in domains:
            for t in d["tables"]:
                if t not in seen:
                    tables.append(t)
                    seen.add(t)
        return tables

    # ── 全量 DDL 注入 ──────────────────────────────────────────────────────────────────

    def inject(
        self,
        user_question: str,
        top_k: int = 10,
        max_chars: int = 4000,
        include_warning: bool = True,
    ) -> str:
        """
        [V90.5] 分区分层注入：根据问题分类定位目标表，注入该表全量字段 DDL。
        区别于 V80.0：
        - 旧版：所有表混在一起，top-k 关键词匹配 -> 遗漏字段 -> 幻觉
        - 新版：先分类定表，再注入该表全部字段 -> 零遗漏 -> 零幻觉
        """
        if not user_question or not user_question.strip():
            return self._format_warning() if include_warning else ""

        domains = self.classify(user_question)
        target_tables = self.get_target_tables(user_question)

        if not target_tables:
            target_tables = _DEFAULT_TABLES

        # 构造物理表 DDL
        lines = []
        domain_desc = domains[0]["desc"] if domains else "通用"
        lines.append(
            f"**[Schema 物理真相 — 数据域 {domain_desc}]**\n"
            f"以下为目标表的**完整物理字段清单**。你只能使用这些字段，严禁编造任何不在此列表中的字段名。\n"
            f"如需统计值请使用 `COUNT(*) AS xxx`, `SUM(col) AS xxx` 形式创建别名。\n"
        )

        metadata = schema_manager.get_metadata()
        total_injected = 0

        for table_name in target_tables:
            table_fields = [m for m in metadata if m.get("table", "").upper() == table_name.upper()]

            if not table_fields:
                # 尝试从 Cache 获取（metadata 可能没有但 Cache 有）
                cache_cols = schema_manager._schema_cache.get(table_name.upper(), [])
                if cache_cols:
                    table_fields = [{"field": c, "type": "", "desc": c, "table": table_name} for c in cache_cols]

            if not table_fields:
                continue

            lines.append(f"\n### 物理表 `{table_name}` ({len(table_fields)} 个字段)")
            lines.append("| 字段名 | 类型 | 说明 |")
            lines.append("|--------|------|------|")

            for f in table_fields:
                fname = f["field"]
                ftype = f.get("type", "")
                fdesc = f.get("desc", fname)
                lines.append(f"| `{fname}` | {ftype} | {fdesc} |")
                total_injected += 1

        if total_injected == 0:
            return self._format_warning() if include_warning else ""

        # ── [V116.0] 审计治理与安全禁区 (Audit Governance) ──────────────────
        from app.core.schema_registry import schema_registry
        forbidden_tables = schema_registry.get_forbidden_table_names()
        valid_prefixes = schema_registry.get_valid_prefixes()
        sensitive_fields = schema_registry.get_sensitive_fields()

        lines.append("\n## 🚨 [审计治理与安全禁区 - 强制合规提示]")
        lines.append(f"- **禁止访问的幻觉表**: {', '.join([f'`{t}`' for t in forbidden_tables])} (严禁猜测，这些表物理不存在或被禁止直接访问。)")
        lines.append(f"- **合法表前缀**: 物理表名必须以 {', '.join([f'`{p}`' for p in valid_prefixes])} 开头。)")
        lines.append(f"- **敏感字段约束**: 涉及 {', '.join([f'`{f}`' for f in sensitive_fields])} 字段时，严禁输出明文，必须用于过滤或由系统自动脱敏。)")
        lines.append("- **性能强制分区**: 涉及明细表查询时，**必须** 显式包含 `setl_time` 时间范围过滤条件（推荐 2024 年内）。")

        # 追加约束提示
        lines.append(
            f"\n**[物理约束总结]** 以上共注入 {total_injected} 个物理字段。你只能使用上述物理列。"
            f"严禁在 WHERE/JOIN 中臆造任何字段名，否则将触发安全策略拦截。"
        )

        result = "\n".join(lines)
        logger.info(f"[SchemaInjector] 物理 Schema 注入: 域 {domain_desc} 表 {target_tables} 字段数 {total_injected} (已注入治理元数据)")
        return result[:max_chars] if len(result) > max_chars else result

    # ── 兼容旧接口 ──────────────────────────────────────────────────────────────────

    def inject_topk(
        self,
        user_question: str,
        top_k: int = 10,
        max_chars: int = 1200,
        include_warning: bool = True,
    ) -> str:
        """[向后兼容] V80.0 风格的 Top-K 注入（仅在特殊场景使用）"""
        if not user_question or not user_question.strip():
            return self._format_warning() if include_warning else ""

        seeds = self._get_all_seeds()
        scored = self._score_fields(user_question, seeds)
        top_fields = scored[:top_k]

        if not top_fields:
            return self._format_warning() if include_warning else ""

        lines = ["**[Schema 推荐] 以下为物理库中探测到的相关字段。严禁使用此处未列出的字段：**\n"]
        seen_fields: Set[str] = set()
        for field_dict, score in top_fields:
            fname = field_dict["field"]
            if fname in seen_fields:
                continue
            seen_fields.add(fname)
            table = field_dict.get("table", "")
            desc = field_dict.get("desc", "")
            lines.append(f"- `{fname}` [{table}]: {desc}")

        result = "\n".join(lines)
        return result[:max_chars] if len(result) > max_chars else result

    def get_field_names(self, user_question: str, top_k: int = 10) -> List[str]:
        seeds = self._get_all_seeds()
        scored = self._score_fields(user_question, seeds)
        return [d["field"] for d, _ in scored[:top_k]]

    # ── 内部方法 ─────────────────────────────────────────────────────────────────────

    def _get_all_seeds(self) -> List[Dict]:
        """合并 SchemaManager 的物理元数据与外部文档定义。"""
        if self._extended_seeds is not None:
            return self._extended_seeds

        all_seeds = list(schema_manager.get_metadata())
        for seed in all_seeds:
            if "keywords" not in seed:
                seed["keywords"] = [seed["field"]]
                if seed.get("desc"):
                    seed["keywords"].extend(re.split(r'[，、]', seed["desc"]))

        if self._external_file and os.path.exists(self._external_file):
            try:
                extra = self._parse_external_schema(self._external_file)
                all_seeds.extend(extra)
                logger.debug(f"[SchemaInjector] 外部字典加载完成，新增 {len(extra)} 个字段")
            except Exception as e:
                logger.warning(f"[SchemaInjector] 外部字典解析失败（不影响使用）: {e}")

        self._extended_seeds = all_seeds
        return all_seeds

    def _score_fields(self, user_question: str, seeds: List[Dict]) -> List[Tuple[Dict, float]]:
        text = user_question.lower()
        scored = []
        for seed in seeds:
            score = 0.0
            keywords = seed.get("keywords", [])
            for kw in keywords:
                if kw.lower() in text:
                    score += 2.0
            if seed["field"].lower() in text:
                score += 5.0
            if score > 0:
                scored.append((seed, score))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _parse_external_schema(self, filepath: str) -> List[Dict]:
        extra = []
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        pattern = re.compile(r'\|\s*(`?)(\w+)\1\s*\|[^|]*\|([^|]+)\|')
        for m in pattern.finditer(content):
            fname, desc = m.group(2).strip(), m.group(3).strip()
            if fname and desc and len(fname) > 2:
                extra.append({"field": fname, "desc": desc[:80], "table": "external"})
        return extra

    @staticmethod
    def _format_warning() -> str:
        return "**[Schema 警告] 未检索到物理字段，请确保查询逻辑符合 Physical Blueprint。**"


schema_injector = SchemaInjector(
    external_schema_file="e:/chain/hsa-agent/docs/db_schema_clickhouse.md"
)
