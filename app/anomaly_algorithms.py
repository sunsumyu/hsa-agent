
import os
import json
from loguru import logger

class AnomalyAlgorithmEngine:
    """
    [企业级] 异常审计算法引擎。
    从知识库加载标准化算法模板，支持自适应基线计算。
    """
    def __init__(self, kb_path="configs/audit_knowledge_base.json"):
        self.kb_path = kb_path
        self.algorithms = self._load_algorithms()

    def _load_algorithms(self) -> dict:
        try:
            if os.path.exists(self.kb_path):
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("algorithms", {})
        except Exception as e:
            logger.error(f"加载算法库失败: {e}")
        return {}

    def get_algorithm_sql(self, algo_name: str, **kwargs) -> str:
        """
        获取格式化后的 SQL 模板。
        支持对 limit, threshold, table 等参数的动态注入。
        """
        algo = self.algorithms.get(algo_name)
        if not algo:
            # 兼容旧逻辑映射
            return ""
        
        template = algo.get("sql", "")
        try:
            # 自动补全默认值
            params = {"limit": 100, "days": 3, "table": "fqz_gz_jzsj_all_ql", "threshold": 0}
            params.update(kwargs)
            return template.format(**params)
        except KeyError as e:
            logger.warning(f"算法 {algo_name} 缺少必要参数: {e}")
            return template

    def format_anomaly_report(self, algo_name: str, data: list) -> str:
        """格式化审计报告摘要"""
        count = len(data)
        desc = self.algorithms.get(algo_name, {}).get("desc", algo_name)
        return f"【物理异常检测】算法 {desc} 执行成功，在物理库中检出 {count} 条潜在异常线索。建议执行穿透式明细复核。"
            
    def list_algorithms(self) -> list:
        return [{"name": k, "desc": v.get("desc")} for k, v in self.algorithms.items()]

# 模块级单例 (保持与 tools.py 兼容)
anomaly_detector = AnomalyAlgorithmEngine()
