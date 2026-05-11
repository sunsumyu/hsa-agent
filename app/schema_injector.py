"""
app/schema_injector.py
======================
[企业级可复用模块] 精准 Schema 注入器 (M4)

解决问题：
    当前每次 LLM 调用时，Prompt 携带完整的数据库 Schema（可能数千 token），
    大部分字段与当前任务完全无关，导致：
    1. 输入 Token 暴增（成本不可持续）
    2. LLM 注意力被无关字段分散，增加幻觉风险
    3. 上下文窗口被无谓占用

解决方案（来自 Vellum/Anthropic 最佳实践）：
    "不传入全量 Schema，而是根据任务关键词 RAG 检索相关的
     Table Definitions 和 Business Formulas"

设计原则：
    - 零业务依赖：不 import 任何审计、医保相关模块
    - 懒加载：字典只在第一次被访问时加载
    - 可配置：top_k、最大字符数均可调参
    - 可独立测试：不依赖完整 Agent 图

使用方式：
    from app.schema_injector import schema_injector

    # 注入精准 Schema（替代全量 Schema 堆砌）
    schema_hint = schema_injector.inject(
        user_question="核查同一患者是否存在重复住院",
        top_k=5,
        max_chars=600
    )
    # => "- fixmedins_code: 医疗机构编码（不能用 hosp_code）\n- psn_no: 参保人唯一标识..."
"""

from __future__ import annotations

import os
import re
from typing import List, Dict, Optional, Tuple
from loguru import logger


# ──────────────────────────────────────────────────────────
# 核心字段词典（内置种子，不依赖外部文件时的保底字典）
# ──────────────────────────────────────────────────────────
BUILTIN_FIELD_SEEDS: List[Dict] = [
    # 主要核查表字段
    {"field": "fixmedins_code",   "alias": ["医院编码", "机构编码"], "desc": "医疗机构唯一编码（物理字段，严禁猜测为 hosp_code）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["医院", "机构", "医疗机构", "医保定点"]},
    {"field": "fixmedins_name",   "alias": ["医院名称", "机构名称"], "desc": "医疗机构名称", "table": "fqz_gz_jzsj_all_ql", "keywords": ["医院", "机构", "医院名"]},
    {"field": "psn_no",           "alias": ["参保人ID", "患者编号"], "desc": "参保人唯一标识（主要关联字段）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["参保人", "患者", "人员", "个人"]},
    {"field": "psn_name",         "alias": ["姓名", "患者姓名"], "desc": "参保人姓名（存在乱码，建议仅用于展示）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["姓名", "患者姓名", "人员姓名"]},
    {"field": "gend",             "alias": ["性别"], "desc": "性别代码：1=男，2=女（必须使用此物理字段，严禁猜测为 gender）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["性别", "男", "女", "妇科", "性别冲突"]},
    {"field": "age",              "alias": ["年龄"], "desc": "参保人年龄", "table": "fqz_gz_jzsj_all_ql", "keywords": ["年龄"]},
    {"field": "certno",           "alias": ["身份证号", "证件号码"], "desc": "参保人身份证号", "table": "fqz_gz_jzsj_all_ql", "keywords": ["身份证", "证件号"]},
    {"field": "dise_name",        "alias": ["疾病名称", "诊断", "病名"], "desc": "主要诊断名称（用于性别冲突、疾病筛查）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["诊断", "疾病", "病名", "妇科", "男科", "子宫", "前列腺"]},
    {"field": "start_date",       "alias": ["入院日期", "开始日期"], "desc": "住院开始日期（用于住院时间段计算）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["入院", "住院开始", "住院时间", "重复住院", "分解住院"]},
    {"field": "end_date",         "alias": ["出院日期", "结束日期"], "desc": "住院结束日期（用于住院时间段计算）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["出院", "住院结束", "住院时间", "重复住院", "分解住院"]},
    {"field": "setl_time",        "alias": ["结算时间", "结算日期"], "desc": "医疗费用结算时间", "table": "fqz_gz_jzsj_all_ql", "keywords": ["结算", "时间", "日期", "同一天"]},
    {"field": "setl_id",          "alias": ["结算ID", "结算流水号"], "desc": "结算流水唯一标识", "table": "fqz_gz_jzsj_all_ql", "keywords": ["结算ID", "流水", "唯一", "去重"]},
    {"field": "medfee_sumamt",    "alias": ["医疗总费用", "结算金额"], "desc": "医疗总费用（必须使用此物理字段，严禁猜测为 total_fee 或 total_amount）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["费用", "金额", "总额", "报销", "花费"]},
    {"field": "fund_pay_sumamt",  "alias": ["医保支付", "基金支付", "报销金额"], "desc": "医保基金实际支付金额（核查骗保的核心字段）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["医保支付", "基金", "报销", "骗保", "违规金额"]},
    {"field": "med_type",         "alias": ["就医类型", "医疗类型"], "desc": "就医类型：定点药店购药、门诊、住院等", "table": "fqz_gz_jzsj_all_ql", "keywords": ["类型", "药店", "门诊", "住院", "购药"]},
    {"field": "addr",             "alias": ["地址", "联系地址"], "desc": "参保人地址（用于聚集性就医网络分析）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["地址", "联系", "共用", "聚集"]},
    {"field": "certno",           "alias": ["身份证号", "证件号"], "desc": "证件号（存在乱码，建议使用 psn_no）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["身份证", "证件", "实名"]},
    # 统计分析表
    {"field": "vix",              "alias": ["变异指数"], "desc": "医疗机构变异指数（越高表示异常程度越大）", "table": "fqz_all_yy_yd_1", "keywords": ["变异", "离散", "异常", "机构风险"]},
    # [V68.8] 目录与明细扩展字段（用于性别冲突等精准核查）
    {"field": "nat_hi_druglist_memo", "alias": ["目录备注", "限用说明"], "desc": "国家医保目录限定支付范围备注", "table": "fqz_drug_mcs_info_list", "keywords": ["备注", "限女性", "限儿童", "支付范围"]},
    {"field": "hilist_name",          "alias": ["项目名称", "药品名称"], "desc": "费用明细项目名称", "table": "fqz_gz_jzsj_all_ql", "keywords": ["药品", "项目", "名称"]},
    {"field": "hilist_code",          "alias": ["项目编码", "医保编码"], "desc": "费用明细项目编码", "table": "fqz_gz_jzsj_all_ql", "keywords": ["编码", "代码", "项目", "服务", "收费项目"]},
    {"field": "med_list_code",        "alias": ["通用目录编码"], "desc": "国家统一医保目录编码", "table": "fqz_drug_mcs_info_list", "keywords": ["目录编码", "国家编码"]},
    {"field": "det_item_fee_sumamt",  "alias": ["明细金额", "项目金额"], "desc": "费用明细条目金额", "table": "fqz_gz_jzsj_all_ql", "keywords": ["金额", "明细"]},
    {"field": "tel",                  "alias": ["手机号", "联系方式"], "desc": "参保人手机号（若表中缺失，请调用 query_fraud_ring 查图）", "table": "fqz_gz_jzsj_all_ql", "keywords": ["手机号", "联系方式", "电话", "共用"]},
]


class SchemaInjector:
    """
    精准 Schema 注入器。

    根据用户问题的语义，从字段词典中召回最相关的 N 个字段，
    生成简洁的 Schema Hint 字符串，用于替代 Prompt 中的全量 Schema。
    """

    def __init__(
        self,
        field_seeds: Optional[List[Dict]] = None,
        external_schema_file: Optional[str] = None,
    ):
        """
        Args:
            field_seeds: 自定义字段种子列表。不传则使用内置种子。
            external_schema_file: 可选的外部 Markdown Schema 文档路径。
                                  如果提供，会尝试从中额外解析字段。
        """
        self._seeds = field_seeds or BUILTIN_FIELD_SEEDS
        self._external_file = external_schema_file
        self._extended_seeds: Optional[List[Dict]] = None  # 懒加载

    def inject(
        self,
        user_question: str,
        top_k: int = 6,
        max_chars: int = 800,
        include_warning: bool = True,
    ) -> str:
        """
        根据用户问题生成精准的 Schema Hint。

        Args:
            user_question: 用户输入的审计任务描述
            top_k: 最多返回多少个相关字段
            max_chars: 输出的最大字符数（防止意外过长）
            include_warning: 是否在开头包含"禁止猜字段名"的提示

        Returns:
            格式化的 Schema Hint 字符串，可直接注入 Prompt
        """
        if not user_question or not user_question.strip():
            return self._format_warning() if include_warning else ""

        seeds = self._get_all_seeds()
        scored = self._score_fields(user_question, seeds)
        top_fields = scored[:top_k]

        if not top_fields:
            return self._format_warning() if include_warning else ""

        lines = []
        if include_warning:
            lines.append("**[Schema 推荐] 以下为与任务相关的物理字段提示。若无法满足查询需求（如需核查手机号、社会关系等），请务必调用 get_table_schema 或 query_fraud_ring 获取完整结构：**\n")

        seen_fields = set()
        for field_dict, score in top_fields:
            fname = field_dict["field"]
            if fname in seen_fields:
                continue
            seen_fields.add(fname)

            table = field_dict.get("table", "")
            desc = field_dict.get("desc", "")
            aliases = field_dict.get("alias", [])
            alias_str = f"（别名参考：{', '.join(aliases[:2])}）" if aliases else ""

            lines.append(f"- `{fname}` [{table}]: {desc}{alias_str}")

        result = "\n".join(lines)
        return result[:max_chars] if len(result) > max_chars else result

    def get_field_names(self, user_question: str, top_k: int = 8) -> List[str]:
        """
        只返回相关字段名列表（不含描述），适合用于 SQL 校验。

        Returns:
            List[str] 字段名列表
        """
        seeds = self._get_all_seeds()
        scored = self._score_fields(user_question, seeds)
        return [d["field"] for d, _ in scored[:top_k]]

    # ──────────────────────────────────────────────────────
    # 私有方法
    # ──────────────────────────────────────────────────────

    def _score_fields(
        self, user_question: str, seeds: List[Dict]
    ) -> List[Tuple[Dict, float]]:
        """对每个字段计算与 user_question 的相关性分数"""
        text = user_question.lower()
        scored = []

        for seed in seeds:
            score = 0.0
            keywords = seed.get("keywords", [])
            aliases = seed.get("alias", [])
            desc = seed.get("desc", "")

            # 关键词命中（每命中一个 +2 分）
            for kw in keywords:
                if kw.lower() in text:
                    score += 2.0

            # 别名命中（+1.5 分）
            for alias in aliases:
                if alias.lower() in text:
                    score += 1.5

            # 描述词命中（+0.5 分）
            for word in desc.split("（")[0].split("，"):
                if word.strip() and word.strip().lower() in text:
                    score += 0.5

            # 字段名本身出现在问题中（+3 分，最高优先级）
            if seed["field"].lower() in text:
                score += 3.0

            if score > 0:
                scored.append((seed, score))

        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _get_all_seeds(self) -> List[Dict]:
        """获取全部字段种子（内置 + 外部文件解析，懒加载）"""
        if self._extended_seeds is not None:
            return self._extended_seeds

        all_seeds = list(self._seeds)

        if self._external_file and os.path.exists(self._external_file):
            try:
                extra = self._parse_external_schema(self._external_file)
                all_seeds.extend(extra)
                logger.debug(f"[SchemaInjector] 外部字典加载完成，新增 {len(extra)} 个字段")
            except Exception as e:
                logger.warning(f"[SchemaInjector] 外部字典解析失败（不影响使用）: {e}")

        self._extended_seeds = all_seeds
        return all_seeds

    def _parse_external_schema(self, filepath: str) -> List[Dict]:
        """从 Markdown Schema 文档中解析额外字段"""
        extra = []
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        # 匹配 `| field_name | type | description |` 格式的 Markdown 表格行
        pattern = re.compile(r'\|\s*(`?)(\w+)\1\s*\|[^|]*\|([^|]+)\|')
        for m in pattern.finditer(content):
            fname = m.group(2).strip()
            desc = m.group(3).strip()
            if fname and desc and len(fname) > 2:
                extra.append({
                    "field": fname,
                    "alias": [],
                    "desc": desc[:80],
                    "table": "external",
                    "keywords": desc.split("，")[:3],
                })
        return extra

    @staticmethod
    def _format_warning() -> str:
        return "**[Schema 警告] 未检索到相关字段，请使用 get_table_schema 工具获取准确字段列表。**"


# 模块级单例
schema_injector = SchemaInjector(
    external_schema_file="e:/chain/hsa-agent-python/docs/db_schema_clickhouse.md"
)
