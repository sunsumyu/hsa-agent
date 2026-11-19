"""
Semantic Encyclopedia Parser Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates markdown parsing,
seed semantics, regional tagging, domain block splitting, and table-level
metadata extraction behind a clean API.
"""
import os
import re
from typing import List, Dict, Any, Optional
from loguru import logger


class SemanticEncyclopediaParser:
    """从医保审计百科文档中提取物理表及字段语义元数据"""

    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    _DEFAULT_SCHEMA_FILE = os.path.join(_REPO_ROOT, "docs", "medical_audit_encyclopedia.md")

    def __init__(self, schema_file: Optional[str] = None):
        self.schema_file = schema_file or self._DEFAULT_SCHEMA_FILE
        self.model_name = "BAAI/bge-small-zh-v1.5"

    def extract_metadata(self) -> List[Dict[str, Any]]:
        """解析百科文档，提取全域 32 表分区业务含义与核心种子"""
        CORE_SEMANTIC_SEEDS = [
            {"table": "v_audit_hospital_monthly", "column": "total_amount", "desc": "医院报销排行榜，医疗机构总金额排名，费用趋势, 医院月度统计, 大盘数据"},
            {"table": "v_audit_patient_annual", "column": "annual_amount", "desc": "个人年度总费用，患者年度风险画像，高频就医, 跨院套现识别, 年度行为分析"},
            {"table": "fqz_all_yy_yd_1", "column": "setl_time", "desc": "结算时间, 入院时间, 就医结算日期, 年度统计, 跨年分析, 近几年"},
            {"table": "fqz_all_yy_yd_1", "column": "medfee_sumamt", "desc": "医疗总金额，结算金额, 费用总额, 统筹支付底盘, 高风险大额监控"},
            {"table": "fqz_all_yy_yd_1", "column": "hifp_pay", "desc": "统筹基金支付, 医保报销金额, 审计骗保监控对象, 核心违规金额"},
            {"table": "fqz_all_yy_yd_1", "column": "vix", "desc": "变异指数, 离散系数, 异常增长风险标识, 高风险指标, 离群点识别"},
            {"table": "fqz_all_yy_yd_1", "column": "psn_no", "desc": "个人编号, 患者 ID, 参保人标识, 人员轨迹分析"},
            {"table": "fqz_all_yy_yd_1", "column": "ipt_days", "desc": "住院天数, 入院时长, 分解住院风险"},
        ]

        extracted_data = []
        for seed in CORE_SEMANTIC_SEEDS:
            full_text = f"表 {seed['table']} 的字段 {seed['column']} 核心含义是 {seed['desc']}"
            extracted_data.append({**seed, "type": "Core", "full_text": full_text})

        if not os.path.exists(self.schema_file):
            logger.warning(f"百科字典文件缺失: {self.schema_file}，使用核心种子降级")
            return extracted_data

        try:
            with open(self.schema_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"读取百科字典失败: {e}")
            return extracted_data

        # 逻辑：按 Domain (📂) 进行初步物理划分，然后按子标题 (###) 拆分表
        domain_blocks = re.split(r"## 📂 ", content)[1:]

        for dom_block in domain_blocks:
            domain_name_match = re.search(r"^(.*?)\n", dom_block)
            domain_name = domain_name_match.group(1).strip() if domain_name_match else "未知域"

            # 拆分表块
            table_blocks = re.split(r"### ", dom_block)[1:]
            for block in table_blocks:
                title_line = block.split("\n")[0]
                table_match = re.search(r"(fqz_[^\s-]+)", title_line)
                if not table_match:
                    continue
                table_name = table_match.group(1)
                table_desc = title_line.replace(table_name, "").strip(" .-\t")

                summary_match = re.search(r"【业务价值】：(.*?)\n", block)
                table_summary = summary_match.group(1) if summary_match else table_desc

                # 解析 Markdown 表格格式
                rows = re.findall(
                    r"\|\s*`?([^`\|]+?)`?\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]*?)\s*\|",
                    block,
                )
                for r in rows:
                    col = r[0].strip()
                    if col in ["物理字段", "字段名", ":---"]:
                        continue
                    desc = r[1].strip() if len(r) > 1 else "业务字段"
                    dtype = r[2].strip() if len(r) > 2 else "String"
                    meaning = r[3].strip() if len(r) > 3 else ""
                    extracted_data.append(
                        self._make_semantic_item(
                            domain_name, table_name, table_summary, col, desc, meaning, dtype
                        )
                    )

                # 解析无序列表格式
                bullet_matches = re.findall(r"-\s*\*\*`?([^`\s\*]+)`?\*\*[:：]\s*(.*?)\n", block)
                for col, desc in bullet_matches:
                    extracted_data.append(
                        self._make_semantic_item(
                            domain_name, table_name, table_summary, col, desc, "列表定义"
                        )
                    )

        # 全局通用字典注入 (针对 Domain B)
        common_metrics_match = re.search(r"## 🏛️ 通用业务指标字典 (.*?)\n(.*?)\n##", content, re.DOTALL)
        if common_metrics_match:
            common_text = common_metrics_match.group(2)
            metrics = re.findall(r"-\s*\*\*`?([^`\s\*]+)`?\*\*[:：]\s*(.*?)\n", common_text)
            b_tables = {
                item["table"]
                for item in extracted_data
                if item.get("domain") == "CGZHAN - Production Stats"
            }
            for t_name in b_tables:
                for col, desc in metrics:
                    extracted_data.append(
                        self._make_semantic_item(
                            "General", t_name, "通用统计维度", col, desc, "继承自全局字典"
                        )
                    )

        logger.info(f"✅ 百科语义捕获完成: 共激活 {len(extracted_data)} 个审计知识锚点。")
        return extracted_data

    def _make_semantic_item(
        self, domain: str, table: str, summary: str, col: str, desc: str, meaning: str, dtype: str = "String"
    ) -> Dict[str, Any]:
        region = "GLOBAL"
        region_match = re.search(r"\[(.*?)\]", desc)
        if region_match:
            region = region_match.group(1)

        full_text = f"[{domain}] [{region}] 表 {table} ({summary}) 的字段 {col} (类型: {dtype}) 含义是 {desc}。审计价值 {meaning}"
        return {
            "domain": domain,
            "table": table,
            "column": col,
            "region": region,
            "type": dtype,
            "desc": f"{desc} {meaning}",
            "full_text": full_text,
        }
