import ast
from typing import List, Dict, Any, Tuple
import re
from loguru import logger

class PrecisionBooster:
    """[V36.0] 物理计算助推器：实现审计数值的确定性计算"""
    
    @staticmethod
    def calculate_hard_metrics(raw_data_str: str) -> Tuple[float, int, List[float]]:
        """
        [V60.0] 物理加固：支持 Markdown 表格与 JSON 混合解析。
        [V60.0 P1 修复] 增加数据有效性守啹：排除异常消息、空返回、Coroutine repr 等假数据。
        """
        if not raw_data_str or raw_data_str == "[]" or "无查询结果" in raw_data_str:
            return 0.0, 0, []

        # [V60.0 P1] 有效性守啹：以下任何一个信号出现，说明 raw_data 并非真实查询结果
        _EMPTY_SIGNALS = [
            "查询成功，返回 0 条",  # execute_audit_sql 的常规空结果描述
            "查询失败",              # 连接失败或 SQL 错误
            "审计异常",              # Agent 强制终止输出
            "审计说明",              # NEED_SCHEMA 兄底输出
            "<coroutine",            # 异步函数未被 await 正确调用的兼容守啹
            "object at 0x",         # Python 对象 repr （另一种 coroutine 表现）
            "物理探测异常",            # 工具内部运行异常
            "物理引擎执行受阻",        # 工具返回的您需要口径错误
        ]
        for sig in _EMPTY_SIGNALS:
            if sig in raw_data_str:
                logger.debug(f"[Booster P1] 检测到空/异常信号「{sig}」，跳过数据解析")
                return 0.0, 0, []

        try:
            amount_keys = ["medfee", "fee", "amt", "amount", "sum", "cost", "total", "money", "金额", "费用", "总计"]
            count_keys = ["count", "times", "num", "cnt", "次数", "数量"]
            
            lines = [l.strip() for l in raw_data_str.split("\n") if "|" in l and "---" not in l]
            rows_data = []

            if len(lines) >= 2 and ("查询结果" in lines[0] or any(ak in lines[0].lower() for ak in amount_keys + ["psn_no", "id"])):
                # 表格模式解析
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
                            # 过滤非数字字符
                            val_str = "".join(c for c in val_str if c.isdigit() or c == ".")
                            if val_str: row_dict[h] = float(val_str)
                        except: continue
                    if row_dict: rows_data.append(row_dict)
            
            # 如果表格解析失败，尝试 JSON 模式
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

            evidence_items = []
            total_sum = 0.0
            
            if not rows_data:
                logger.debug(f"[V37.6] 进入兜底正则模式，原始数据片段: {raw_data_str[:200]}")
                # [V37.6] 超强力捕获：支持整数和 1-4 位小数
                all_nums = re.findall(r"[:\s](-?\d+(?:\.\d+)?)[,\s\}]", raw_data_str)
                for n in all_nums:
                    try:
                        v = float(n)
                        # 排除 psn_no (通常 8 位以上整数) 或年份
                        if 0.01 < v < 100000000: evidence_items.append(v)
                    except: continue
                
                total_val = sum(evidence_items)
                logger.info(f"[V37.6] 兜底捕获结果: SUM={total_val}, COUNT={len(evidence_items)}")
                return round(total_val, 2), (1 if total_val > 0 else 0), sorted(list(set(evidence_items)), reverse=True)

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
                # 记录该行的其他数值作为证据
                for k, v in row.items():
                    if v != best_val and v > 0: evidence_items.append(v)
            
            evidence_items = sorted(list(set(evidence_items)), reverse=True)
            logger.info(f"[V37.0 Booster] 物理取证完成: SUM={total_sum:.2f}, ITEMS={len(evidence_items)}")
            return round(total_sum, 2), len(rows_data), evidence_items
            
        except Exception as e:
            logger.error(f"[V36.6 Booster] 解析失败: {e}")
            return 0.0, 0, []

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
