import ast
from typing import List, Dict, Any, Tuple, Optional
import re
from loguru import logger

class DataExtractionError(Exception):
    """[V62.0] 物理提取异常：当数据阴影或解析失败时抛出，拒绝静默兜底"""
    pass

class PrecisionBooster:
    """[V62.0] 物理计算助推器：实现审计数值的确定性计算，严禁静默兜底"""
    
    @staticmethod
    def calculate_hard_metrics(raw_data_str: str) -> Tuple[float, int, List[float]]:
        """
        [V62.0 强约束重构] 完全废除正则兜底，实现类似 Result<Data, Error> 的强校验。
        如果无法解析出标准表格或 JSON，直接抛出异常，倒逼状态机熔断。
        """
        if not raw_data_str or raw_data_str == "[]" or "无查询结果" in raw_data_str:
            return 0.0, 0, []

        _EMPTY_SIGNALS = [
            "查询失败", "审计异常", "审计说明", "<coroutine", "object at 0x", "物理探测异常", "物理引擎执行受阻"
        ]
        for sig in _EMPTY_SIGNALS:
            if sig in raw_data_str:
                logger.error(f"[Booster] 检测到脏数据流（Data Shadowing）: {sig}")
                raise DataExtractionError(f"严重状态机错误：上游传递了非结构化脏数据 ({sig})，拒绝生成 0 值幻觉。")

        try:
            amount_keys = ["medfee", "fee", "amt", "amount", "sum", "cost", "total", "money", "金额", "费用", "总计"]
            count_keys = ["count", "times", "num", "cnt", "次数", "数量"]
            
            # ── Step 1: 多级结构化解析 [V89.0] ──────────────────────────────────
            rows_data = []
            import json as _json
            import ast as _ast
            import datetime as _dt
            from decimal import Decimal as _Decimal

            # 1.1 尝试 JSON 直接解析
            try:
                # 清洗字符串中的非法控制字符
                clean_str = re.sub(r'[\x00-\x1f\x7f]', '', raw_data_str).strip()
                if clean_str.startswith("[") or clean_str.startswith("{"):
                    parsed = _json.loads(clean_str)
                    rows_data = parsed if isinstance(parsed, list) else [parsed]
            except (ValueError, KeyError):
                pass

            # 1.2 尝试 ast.literal_eval 解析 (处理 Python 特有类型)
            if not rows_data:
                try:
                    eval_context = {"datetime": _dt, "date": _dt.date, "Decimal": _Decimal}
                    parsed = _ast.literal_eval(raw_data_str.strip())
                    rows_data = parsed if isinstance(parsed, list) else [parsed]
                except (ValueError, SyntaxError):
                    pass

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
                    if row_dict: rows_data.append(row_dict)

            # [V89.0] 强校验门禁：如果数据流不为空但解析不到任何记录，触发熔断
            if not rows_data and raw_data_str.strip() not in ["[]", ""]:
                logger.error(f"[Booster] 解析失败。原始数据片段: {raw_data_str[:200]}...")
                raise DataExtractionError("无法从输入流中提取出结构化的记录载荷。")

            evidence_items = []
            total_sum = 0.0
            
            for row in rows_data:
                best_val = 0.0
                best_score = 0  # [V97.0] 默认分为 0，只有命中关键词才提取
                for k, v in row.items():
                    k_lower = k.lower()
                    # 排除掉明显的标识符字段
                    if any(id_k in k_lower for id_k in ["no", "id", "code", "certno", "tel", "phone"]):
                        continue
                        
                    try:
                        curr_val = float(str(v).replace(",", ""))
                        score = 0
                        if any(ak in k_lower for ak in amount_keys): score = 30
                        elif any(ck in k_lower for ck in count_keys): score = 15
                        
                        if score > best_score:
                            best_score, best_val = score, curr_val
                    except (ValueError, TypeError):
                        continue
                
                total_sum += best_val
                if best_val > 0:
                    evidence_items.append(best_val)
            
            evidence_items = sorted(list(set(evidence_items)), reverse=True)
            logger.info(f"[Booster] 物理取证严格校验通过: SUM={total_sum:.2f}, COUNT={len(rows_data)}")
            return round(total_sum, 2), len(rows_data), evidence_items
            
        except DataExtractionError as de:
            raise de
        except Exception as e:
            logger.error(f"[Booster] 致命解析错误: {e}")
            raise DataExtractionError(f"数据解析层崩溃: {e}")

    @staticmethod
    def parse_table_to_rows(raw_data_str: str) -> List[Dict[str, Any]]:
        """
        [V36.0] 物理提取：将 Markdown/JSON 原始字符串转化为结构化列表。
        """
        if not raw_data_str or "无查询结果" in raw_data_str: return []
        
        lines = [l.strip() for l in raw_data_str.split("\n") if "|" in l and "---" not in l]
        rows_data = []
        
        # 表格模式
        if len(lines) >= 2:
            header_line = lines[0].replace("查询结果:", "").strip()
            headers = [h.strip().lower() for h in header_line.split("|")]
            for line in lines[1:]:
                if "系统提示" in line or not line.strip(): continue
                cols = [c.strip() for c in line.split("|")]
                if len(cols) != len(headers): continue
                row_dict = {}
                for i, h in enumerate(headers):
                    try:
                        val_str = cols[i].replace(",", "")
                        if re.match(r"^-?\d+(\.\d+)?$", val_str):
                            row_dict[h] = float(val_str)
                        else:
                            row_dict[h] = val_str
                    except (ValueError, TypeError): row_dict[h] = cols[i]
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
                        else: row_dict[key] = val
                    except (ValueError, TypeError): row_dict[key] = val
                rows_data.append(row_dict)
                
        return rows_data

    @staticmethod
    def detect_anomalous_consistency(rows_data: List[Dict[str, Any]]) -> Optional[str]:
        """[V111.0] 异常一致性回溯：检测伪造数据的典型特征"""
        if not rows_data or len(rows_data) < 5: return None
        
        # 收集数值字段
        field_values = {}
        for row in rows_data:
            for k, v in row.items():
                try:
                    curr_val = float(str(v).replace(",", ""))
                    if k not in field_values: field_values[k] = []
                    field_values[k].append(curr_val)
                except:
                    continue
        
        for field, values in field_values.items():
            # 这里的逻辑是：如果一个业务字段在所有记录中都完全相同，且数值很大，通常是逻辑错误（如笛卡尔积或 AI 幻觉）
            if len(values) == len(rows_data) and len(set(values)) == 1:
                const_val = values[0]
                if abs(const_val) > 10 and not (1900 < const_val < 2100):
                    # 特别针对 QA-01 报告中 item_count=14848 的幻觉
                    return f"🚨 [数据幻觉警告] 字段 `{field}` 的所有 {len(values)} 条记录数值均为完全一致的 {const_val}。这在医保审计中属于高度异常，通常由错误的 GROUP BY 或 SQL 笛卡尔积产生。请修正 SQL 逻辑，严禁提交包含‘虚假整齐’数据的报告。"
        return None

    @staticmethod
    def verify_evidence_grounding(report_findings: List[Any], raw_data_list: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        [V111.0] 证据溯源校验 (Fact-Check Pinning)
        确保 Report 中的 Finding 至少能在 Raw Data 中找到影子。
        """
        if not report_findings: return True, ""
        if not raw_data_list: return False, "报告声称发现了问题，但原始数据流为空。"

        # 将原始数据转化为扁平字符串池
        data_pool = str(raw_data_list).lower()
        
        hallucinated_findings = []
        for finding in report_findings:
            # 提取 Finding 中的核心标识符 (如 金额、代码、ID)
            finding_text = str(finding).lower()
            # 检查金额是否在数据池中
            amount = getattr(finding, "amount", 0)
            if amount > 0:
                amount_str = f"{amount:.2f}"
                if amount_str not in data_pool and str(int(amount)) not in data_pool:
                    hallucinated_findings.append(f"金额 ¥{amount_str}")
            
            # 检查证据描述中的关键字是否在数据池中
            evidence = getattr(finding, "evidence", "")
            if evidence:
                # 提取可能的 ID (如 P001, S001)
                ids = re.findall(r'[A-Z0-9]{5,}', str(evidence))
                for id_val in ids:
                    if id_val.lower() not in data_pool:
                        hallucinated_findings.append(f"标识符 {id_val}")

        if hallucinated_findings:
            msg = f"❌ [证据链断裂] 报告中提到的证据 ({', '.join(hallucinated_findings)}) 在原始 SQL 结果中找不到对应项。严禁在报告中‘信口雌黄’，请务必仅根据 SQL 返回的物理记录编写结论。"
            logger.error(msg)
            return False, msg
            
        return True, ""

booster = PrecisionBooster()
