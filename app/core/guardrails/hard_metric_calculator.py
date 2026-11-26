"""
Hard Metric & Evidence Grounding Calculator Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates data shadow prevention,
deterministic metric calculations, AST/JSON multi-tier parsing, Cartesian anomaly
fusing, and fact-check grounding pinning behind simple, cohesive interfaces.
"""
import ast
import json
import re
from typing import List, Dict, Any, Tuple, Optional
from loguru import logger


class DataExtractionError(Exception):
    """物理提取异常：当数据阴影或解析失败时抛出，拒绝静默兜底与 0 值幻觉"""
    pass


# 业务常用敏感/聚合字段特征
_AMOUNT_KEYS = ["medfee", "fee", "amt", "amount", "sum", "cost", "total", "money", "金额", "费用", "总计"]
_COUNT_KEYS = ["count", "times", "num", "cnt", "次数", "数量"]
_EMPTY_SIGNALS = [
    "查询失败", "审计异常", "审计说明", "<coroutine", "object at 0x", "物理探测异常", "物理引擎执行受阻"
]
_EXEMPT_FIELD_PATTERNS = {"amt", "fee", "price", "sumamt", "pay", "rate", "money"}
_SUSPICIOUS_COUNT_PATTERNS = {"item_count", "cartesian", "cross_join_cnt", "dup_cnt"}


def calculate_hard_metrics(raw_data_str: str) -> Tuple[float, int, List[float]]:
    """
    物理确定性指标严格计算，实现强校验。
    如果无法解析出标准表格或 JSON，或检测到数据阴影，抛出 DataExtractionError。
    """
    if not raw_data_str or raw_data_str == "[]" or "无查询结果" in raw_data_str:
        return 0.0, 0, []

    for sig in _EMPTY_SIGNALS:
        if sig in raw_data_str:
            logger.error(f"[HardMetricCalculator] 检测到脏数据流（Data Shadowing）: {sig}")
            raise DataExtractionError(f"严重状态机错误：上游传递了非结构化脏数据 ({sig})，拒绝生成 0 值幻觉。")

    try:
        rows_data = []

        # 1.1 尝试 JSON 直接解析
        try:
            clean_str = re.sub(r'[\x00-\x1f\x7f]', '', raw_data_str).strip()
            if clean_str.startswith("[") or clean_str.startswith("{"):
                parsed = json.loads(clean_str)
                rows_data = parsed if isinstance(parsed, list) else [parsed]
        except (ValueError, KeyError) as exc:
            logger.debug(f"[HardMetricCalculator] JSON track fallback: {exc}")

        # 1.2 尝试 ast.literal_eval 解析 (处理 Python 特有类型)
        if not rows_data:
            try:
                parsed = ast.literal_eval(raw_data_str.strip())
                rows_data = parsed if isinstance(parsed, list) else [parsed]
            except (ValueError, SyntaxError) as exc:
                logger.debug(f"[HardMetricCalculator] literal_eval track fallback: {exc}")

        # 1.3 正则兜底 (处理 LLM 混入的杂质)
        if not rows_data:
            kv_pattern = re.compile(r"['\"](?P<key>[^'\"]+)['\"]\s*:\s*(?:Decimal\(')?(?P<val>[^'\"},]+)(?:\')?")
            for item_match in re.finditer(r"\{([^{}]+)\}", raw_data_str):
                row_str = item_match.group(1)
                row_dict = {}
                for kv_match in kv_pattern.finditer(row_str):
                    key = kv_match.group('key').lower()
                    val = kv_match.group('val').strip().strip("'").strip('"')
                    row_dict[key] = val
                if row_dict:
                    rows_data.append(row_dict)

        # 强校验门禁：如果数据流不为空但解析不到任何记录，触发熔断
        if not rows_data and raw_data_str.strip() not in ["[]", ""]:
            logger.error(f"[HardMetricCalculator] 解析失败。原始数据片段: {raw_data_str[:200]}...")
            raise DataExtractionError("无法从输入流中提取出结构化的记录载荷。")

        evidence_items = []
        total_sum = 0.0

        for row in rows_data:
            best_val = 0.0
            best_score = 0
            for k, v in row.items():
                k_lower = k.lower()
                # 排除掉明显的标识符字段
                if any(id_k in k_lower for id_k in ["no", "id", "code", "certno", "tel", "phone"]):
                    continue

                try:
                    curr_val = float(str(v).replace(",", ""))
                    score = 0
                    if any(ak in k_lower for ak in _AMOUNT_KEYS):
                        score = 30
                    elif any(ck in k_lower for ck in _COUNT_KEYS):
                        score = 15

                    if score > best_score:
                        best_score, best_val = score, curr_val
                except (ValueError, TypeError):
                    continue

            total_sum += best_val
            if best_val > 0:
                evidence_items.append(best_val)

        evidence_items = sorted(list(set(evidence_items)), reverse=True)
        logger.info(f"[HardMetricCalculator] 物理取证严格校验通过: SUM={total_sum:.2f}, COUNT={len(rows_data)}")
        return round(total_sum, 2), len(rows_data), evidence_items

    except DataExtractionError as de:
        raise de
    except Exception as e:
        logger.error(f"[HardMetricCalculator] 致命解析错误: {e}")
        raise DataExtractionError(f"数据解析层崩溃: {e}")


def parse_table_to_rows(raw_data_str: str) -> List[Dict[str, Any]]:
    """
    物理提取：将 Markdown/JSON 原始字符串转化为结构化行记录列表。
    """
    if not raw_data_str or "无查询结果" in raw_data_str:
        return []

    lines = [l.strip() for l in raw_data_str.split("\n") if "|" in l and "---" not in l]
    rows_data = []

    # 表格模式
    if len(lines) >= 2:
        header_line = lines[0].replace("查询结果:", "").strip()
        headers = [h.strip().lower() for h in header_line.split("|")]
        for line in lines[1:]:
            if "系统提示" in line or not line.strip():
                continue
            cols = [c.strip() for c in line.split("|")]
            if len(cols) != len(headers):
                continue
            row_dict = {}
            for i, h in enumerate(headers):
                try:
                    val_str = cols[i].replace(",", "")
                    if re.match(r"^-?\d+(\.\d+)?$", val_str):
                        row_dict[h] = float(val_str)
                    else:
                        row_dict[h] = val_str
                except (ValueError, TypeError):
                    row_dict[h] = cols[i]
            rows_data.append(row_dict)

    # JSON 模式兜底
    if not rows_data:
        kv_pattern = re.compile(r"['\"](?P<key>[^'\"]+)['\"]\s*:\s*(?:Decimal\(')?(?P<val>[^'\"]+)(?:\')?")
        for item_match in re.finditer(r"\{([^{}]+)\}", raw_data_str):
            row_str = item_match.group(1)
            row_dict = {}
            for kv_match in kv_pattern.finditer(row_str):
                key = kv_match.group('key').lower()
                val = kv_match.group('val')
                try:
                    if re.match(r"^-?\d+(\.\d+)?$", val):
                        row_dict[key] = float(val)
                    else:
                        row_dict[key] = val
                except (ValueError, TypeError):
                    row_dict[key] = val
            rows_data.append(row_dict)

    return rows_data


def detect_anomalous_consistency(rows_data: List[Dict[str, Any]]) -> Optional[str]:
    """
    异常一致性回溯：仅针对由于多表错误 JOIN / 笛卡尔积导致的【衍生计数爆炸】实施防御。
    豁免真实物理金额与费用列，避免误伤医保定额刷卡/集中结算的真实欺诈特征。
    """
    if not rows_data or len(rows_data) < 5:
        return None

    # 收集数值字段
    field_values: Dict[str, List[float]] = {}
    for row in rows_data:
        for k, v in row.items():
            try:
                curr_val = float(str(v).replace(",", ""))
                if k not in field_values:
                    field_values[k] = []
                field_values[k].append(curr_val)
            except (ValueError, TypeError):
                continue

    for field, values in field_values.items():
        f_lower = field.lower()
        # 若为真实金额或费用字段，予以豁免
        if any(p in f_lower for p in _EXEMPT_FIELD_PATTERNS):
            continue

        # 仅当字段为明确的衍生计数字段且全表恒等爆炸时，才阻断
        is_suspicious_count = any(p in f_lower for p in _SUSPICIOUS_COUNT_PATTERNS)
        if not is_suspicious_count:
            continue

        if len(values) == len(rows_data) and len(set(values)) == 1:
            const_val = values[0]
            if abs(const_val) > 100:
                return (
                    f"🚨 [笛卡尔积计数异常拦截] 派生计数字段 `{field}` 在所有 {len(values)} 条记录中数值均为完全一致的 {const_val}。"
                    "这通常由多表关联未正确 GROUP BY 或笛卡尔积产生，请修正 SQL 关联与去重逻辑。"
                )
    return None


def verify_evidence_grounding(report_findings: List[Any], raw_data_list: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    证据溯源校验 (Fact-Check Pinning)：
    确保 Report 中的 Finding 至少能在 Raw Data 中找到影子，严防信口雌黄。
    """
    if not report_findings:
        return True, ""
    if not raw_data_list:
        return False, "报告声称发现了问题，但原始数据流为空。"

    # 将原始数据转化为扁平字符串池
    data_pool = str(raw_data_list).lower()

    hallucinated_findings = []
    for finding in report_findings:
        amount = getattr(finding, "amount", 0)
        if amount > 0:
            amount_str = f"{amount:.2f}"
            if amount_str not in data_pool and str(int(amount)) not in data_pool:
                hallucinated_findings.append(f"金额 ¥{amount_str}")

        evidence = getattr(finding, "evidence", "")
        if evidence:
            ids = re.findall(r'[A-Z0-9]{5,}', str(evidence))
            for id_val in ids:
                if id_val.lower() not in data_pool:
                    hallucinated_findings.append(f"标识符 {id_val}")

    if hallucinated_findings:
        msg = (
            f"❌ [证据链断裂] 报告中提到的证据 ({', '.join(hallucinated_findings)}) 在原始 SQL 结果中找不到对应项。"
            "严禁在报告中‘信口雌黄’，请务必仅根据 SQL 返回的物理记录编写结论。"
        )
        logger.error(msg)
        return False, msg

    return True, ""
