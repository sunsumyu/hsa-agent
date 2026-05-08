import asyncio
from typing import Type, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from loguru import logger
from app.audit_rules import rule_engine
from app.anomaly_algorithms import anomaly_detector

class RuleExecutionInput(BaseModel):
    rule_id: str = Field(description="The ID or semantic name of the audit rule or anomaly algorithm to run (e.g., 'GENDER_CONFLICT', 'CROSS_HOSPITAL_OVERLAP', 'VIX_ANOMALY_SCAN').")
    extra_filters: Optional[Dict[str, str]] = Field(default=None, description="Optional dynamic filters extracted from the user question.")
    
class RuleExecutionSkill(BaseTool):
    name: str = "run_audit_rule"
    description: str = "Execute a pre-defined deterministic physical audit rule or anomaly detection algorithm on the database."
    args_schema: Type[BaseModel] = RuleExecutionInput

    async def _arun(self, rule_id: str, **kwargs) -> Dict[str, Any]:
        logger.info(f"🔨 [Skill] Executing Rule/Algorithm: {rule_id}")
        
        target_id = ""
        key = rule_id.upper()
        if "GENDER" in key or "性别" in key: target_id = "GENDER_CONFLICT"
        elif "DRUG" in key or "购药" in key: target_id = "HIGH_FREQ_DRUG_PURCHASE"
        elif "DECOMPOSITION" in key or "分解" in key: target_id = "DECOMPOSITION_HOSPITALIZATION"
        elif "CROSS" in key or "重复住院" in key or "同时" in key: target_id = "CROSS_HOSPITAL_OVERLAP"
        elif "REPEAT_BILLING" in key or "重复收费" in key: target_id = "REPEAT_BILLING_DETECTOR"
        elif "CONTACT_SHARING" in key or "联系方式" in key: target_id = "CONTACT_SHARING_DETECTOR"
        elif "VIX" in key or "变异" in key: target_id = "VIX_ANOMALY_SCAN"
        elif "OUTLIER" in key or "离群" in key: target_id = "STATISTICAL_OUTLIER_DETECTOR"
        elif "CLUSTER" in key or "聚集" in key: target_id = "CLUSTER_ENCOUNTER_DETECTOR"
        elif "MAD" in key or "稳健" in key: target_id = "ROBUST_MAD_DETECTOR"
        else: target_id = key
        
        RULE_METADATA = {
            "GENDER_CONFLICT": "【审计方法论】性别冲突校验：穿透结算主表，对费用明细表 (fqz_fymx_test1) 执行逻辑过滤。校验依据：gender='男' 且费用项 (hilist_name) 命中《医保妇产科专属项目清单》关键字。合规依据：《医疗保障基金使用监督管理条例》第十五条。",
            "HIGH_FREQ_DRUG_PURCHASE": "【审计方法论】高频购药核查：按 psn_no 执行窗口聚合。判定标准：自然月内同一药品购药频次 > 4次 或 累计剂量超过临床用药指南 200%。合规依据：《处方管理办法》及医保限额规定。",
            "DECOMPOSITION_HOSPITALIZATION": "【审计方法论】分解住院侦测：通过逻辑 Join 对比相邻住院记录。判定标准：同一患者出院与下次入院间隔时间 <= 15天 且 诊断高度相关。合规依据：《基本医疗保险定点医疗机构服务协议》关于禁止恶意分解住院的条款。",
            "CROSS_HOSPITAL_OVERLAP": "【审计方法论】跨机构重复住院核查：执行时间区间交集运算。判定标准：(A.start <= B.end) AND (A.end >= B.start) 且机构编码不一致。合规依据：医保实时结算管理规定，严禁“同时住院”挂账。",
            "REPEAT_BILLING_DETECTOR": "【审计方法论】重复收费校验：对单次就诊 (setl_id) 执行项目级明细扫描。判定标准：同一项目 (item_code) 的实收数量超过单日限额或物理操作逻辑上线。合规依据：《医疗服务价格目录》。",
            "CONTACT_SHARING_DETECTOR": "【审计方法论】共用联系方式分析：执行关系拓扑聚合。判定标准：同一联系电话 (tel) 挂载 > 2 名参保人且报销总额位于 top 5%。合规依据：打击欺诈骗保专项行动关于团伙作案的识别特征。",
            "VIX_ANOMALY_SCAN": "【审计方法论】VIX 变异指数扫描：采用统计学离群值分析。判定标准：机构均次费用变异系数 (CV) 超过总体均值 3 个标准差。合规依据：医保基金运行监测风险预警指标体系。",
            "CLUSTER_ENCOUNTER_DETECTOR": "【审计方法论】聚集就医图谱挖掘：基于 Neo4j 执行连通分量分析。判定标准：核心节点（医生/药店/手机号）关联的参保人分布密度达到异常阈值。合规依据：医保大数据反欺诈模型规范。"
        }
        methodology = RULE_METADATA.get(target_id, "自定义规则逻辑匹配")
        
        sql = rule_engine.get_rule_sql(target_id, extra_filters=kwargs.get("extra_filters"))
        is_anomaly = False
        if not sql:
            sql = anomaly_detector.get_algorithm_sql(target_id)
            is_anomaly = True
            
        if not sql:
            return {"error": f"Rule or algorithm not found: {rule_id}", "evidence_count": 0}
            
        try:
            from app.tools import _execute_audit_sql_logic
            raw_data = await _execute_audit_sql_logic(sql, return_raw=True)
            if isinstance(raw_data, str) and "失败" in raw_data:
                return {"error": f"Execution blocked: {raw_data}", "evidence_count": 0}
                
            count = len(raw_data) if isinstance(raw_data, list) else 0
            if is_anomaly:
                report_text = anomaly_detector.format_anomaly_report(target_id, raw_data)
            else:
                report_text = rule_engine.format_violation_report(target_id, raw_data)
                
            return {
                "report": report_text,
                "evidence_count": count,
                "raw_evidence": raw_data,
                "methodology": methodology,
                "sql_logic": sql,
                "trace_hint": f"[{'Anomaly' if is_anomaly else 'Rule'} Engine] {methodology} | 命中 {count} 条记录"
            }
        except Exception as e:
            logger.error(f"Rule execution error: {e}")
            return {"error": str(e), "evidence_count": 0}

    def _run(self, rule_id: str) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Cannot use asyncio.run() if a loop is already running
                return loop.create_task(self._arun(rule_id))  # May not be exactly what we want if not awaited, but tools generally prefer async when supported.
        except RuntimeError:
            pass
        return asyncio.run(self._arun(rule_id))
