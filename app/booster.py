import ast
from typing import List, Dict, Any, Tuple
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
            
            lines = [l.strip() for l in raw_data_str.split("\n") if "|" in l and "---" not in l]
            rows_data = []

            # 1. 尝试 Markdown 表格解析
            if len(lines) >= 2 and ("查询结果" in lines[0] or any(ak in lines[0].lower() for ak in amount_keys + ["psn_no", "id"])):
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
                            val_str = "".join(c for c in val_str if c.isdigit() or c == ".")
                            if val_str: row_dict[h] = float(val_str)
                        except: continue
                    if row_dict: rows_data.append(row_dict)
            
            # 2. 尝试 JSON 解析
            if not rows_data:
                kv_pattern = re.compile(r"['\"](?P<key>[^'\"]+)['\"]\s*:\s*(?:Decimal\(')?(?P<val>[\d\.\-]+)(?:\')?")
                for item_match in re.finditer(r"\{([^{}]+)\}", raw_data_str):
                    row_str = item_match.group(1)
                    row_dict = {}
                    for kv_match in kv_pattern.finditer(row_str):
                        key = kv_match.group('key').lower()
                        try:
                            row_dict[key] = float(kv_match.group('val'))
                        except: continue
                    if row_dict: rows_data.append(row_dict)

            # [V62.0 强校验门禁]
            if not rows_data:
                # 废除原有的 re.findall 兜底逻辑
                raise DataExtractionError("无法从输入流中提取出结构化的金额或数值。载荷可能被截断或格式不规范。")

            evidence_items = []
            total_sum = 0.0
            
            for row in rows_data:
                best_val = 0.0
                best_score = -1
                for k, v in row.items():
                    score = 0
                    if any(ak in k for ak in amount_keys): score = 30
                    elif any(ck in k for ck in count_keys): score = 15
                    if score > best_score:
                        best_score, best_val = score, v
                
                total_sum += best_val
                evidence_items.append(best_val)
                for k, v in row.items():
                    if v != best_val and v > 0: evidence_items.append(v)
            
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
                    except: row_dict[h] = cols[i]
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
                    except: row_dict[key] = val
                rows_data.append(row_dict)
                
        return rows_data

booster = PrecisionBooster()
