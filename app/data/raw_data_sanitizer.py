"""
app/data/raw_data_sanitizer.py
==============================
[Matt Pocock Deep Module 实践]
确定性原始证据数据清洗与多轨自愈解析器。

- Interface: 极简，仅暴露唯一的公共契约 sanitize_and_parse(raw_data_str: Any) -> List[Dict[str, Any]]
- Implementation: 内部消化所有底层数据脏杂质：
    1. 物理控制字符与非 ASCII 逃逸序列过滤
    2. Python datetime/date repr 正则重写为标准 ISO 字符串
    3. 多分片 --- 流式聚合
    4. 截断损坏 JSON 的边界自愈还原（json_repair 第四轨兜底，仅在前三轨全败后触发）
- Locality: 将底层数据结构化处理从报表渲染层中剥离出来，各司其职。
"""
from __future__ import annotations

import re
import json
import ast
import datetime
from typing import Any, List, Dict
from loguru import logger


class RawDataSanitizer:
    """确定性原始数据去污与自愈解析深模块 (Deep Module)"""

    @classmethod
    def sanitize_and_parse(cls, raw_data_str: Any) -> List[Dict[str, Any]]:
        """
        唯一的公共契约接口。
        输入：包含脏文本、repr、多分片的原始数据源
        输出：清洗完备、强转为 ISO 格式的字典列表
        """
        if not raw_data_str:
            return []

        # 1. 物理去污
        clean_data = cls._strip_control_chars(raw_data_str)

        # 2. 修复 datetime / date repr
        clean_data = cls._normalize_datetime_repr(clean_data)

        # 3. 多轨解析与损坏自愈
        raw_data_list = cls._parse_multitrack_chunks(clean_data)

        # 4. 类型强转 (ISO 格式化)
        return cls._coerce_iso_formats(raw_data_list)

    @classmethod
    def extract_scan_boundary(
        cls, raw_data_str: Any
    ) -> tuple[Optional[int], Optional[str], Optional[str]]:
        """
        [SSOT] 从原始数据文本或多分片中提取探针物理扫描基数与时空时间范围。
        返回：(total_records, min_time, max_time)
        """
        total_records: Optional[int] = None
        min_time: Optional[str] = None
        max_time: Optional[str] = None

        if not raw_data_str:
            return total_records, min_time, max_time

        clean_data = cls._strip_control_chars(raw_data_str)
        clean_data = cls._normalize_datetime_repr(clean_data)
        rows = cls._parse_multitrack_chunks(clean_data)

        for r in rows:
            if not isinstance(r, dict):
                continue
            cnt_val = (
                r.get("total_cnt")
                or r.get("total_records")
                or r.get("count(*)")
                or r.get("cnt")
            )
            min_val = (
                r.get("min_time")
                or r.get("min_t")
                or r.get("min(setl_time)")
            )
            max_val = (
                r.get("max_time")
                or r.get("max_t")
                or r.get("max(setl_time)")
            )

            if cnt_val is not None:
                try:
                    total_records = int(cnt_val)
                except (ValueError, TypeError) as exc:
                    logger.debug(f"[RawDataSanitizer] scan count cast skipped: {exc}")
            if min_val:
                min_time = str(min_val).split(".")[0].split("T")[0].split(" ")[0]
            if max_val:
                max_time = str(max_val).split(".")[0].split("T")[0].split(" ")[0]

        return total_records, min_time, max_time

    # ──────────────────────────────────────────────────────────────
    # 内部私有实现 (收缩可见范围，对外完全隐匿)
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _strip_control_chars(cls, data_any: Any) -> str:
        if isinstance(data_any, str):
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', data_any)
            return re.sub(r'\\x[0-9a-fA-F]{2}', '', clean)
        return str(data_any)

    @classmethod
    def _normalize_datetime_repr(cls, clean_data: str) -> str:
        def _convert_datetime_repr(match):
            groups = match.groups()
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            if groups[3] is not None:
                hour, minute, second = int(groups[3]), int(groups[4]), int(groups[5])
                out = f'"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"'
                if groups[6] is not None:
                    out = out[:-1] + f'.{int(groups[6]):06d}"'
                return out
            return f'"{year:04d}-{month:02d}-{day:02d}"'

        # 兼容 3/6/7 参数及 tzinfo 等扁平装饰尾参（含 "(" 的嵌套尾参不重写，交由第4轨兜底，防跨括号误吞）
        clean_data = re.sub(
            r'datetime\.datetime\((\d+),\s*(\d+),\s*(\d+)'
            r'(?:,\s*(\d+),\s*(\d+),\s*(\d+))?'
            r'(?:,\s*(\d+))?'
            r'(?:,[^)(]*)?\)',
            _convert_datetime_repr,
            clean_data
        )
        clean_data = re.sub(
            r'datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)',
            lambda m: f'"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"',
            clean_data
        )
        return clean_data

    @classmethod
    def _parse_multitrack_chunks(cls, clean_data: str) -> List[Dict[str, Any]]:
        raw_data_list: List[Dict[str, Any]] = []
        chunks = [c.strip() for c in clean_data.split("---") if c.strip()]
        for chunk in chunks:
            # ── 第1轨：严格 JSON 解析 ──
            if chunk.startswith("[") or chunk.startswith("{"):
                try:
                    parsed = json.loads(chunk)
                    if isinstance(parsed, list):
                        raw_data_list.extend(parsed)
                    elif isinstance(parsed, dict):
                        raw_data_list.append(parsed)
                    continue
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    logger.debug(f"[RawDataSanitizer] Track 1 JSON decode fallback: {exc}")
                # ── 第2轨：Python 字面量解析（单引号 / 尾逗号 / 已归一化的 datetime repr）──
                try:
                    parsed = ast.literal_eval(chunk)
                    if isinstance(parsed, list):
                        raw_data_list.extend(parsed)
                    elif isinstance(parsed, dict):
                        raw_data_list.append(parsed)
                    continue
                except (ValueError, SyntaxError, TypeError) as exc:
                    logger.debug(f"[RawDataSanitizer] Track 2 literal_eval fallback: {exc}")
                # ── 第3轨：防御性自愈，逐个抠取完备对象，防止全量清零 ──
                # 损坏对象按值跳过而非编造（审计语义：缺失可复核，编造即污染对账），但必须留痕
                recovered = False
                recovered_count = 0
                skipped_count = 0
                for obj_match in re.finditer(r'\{[^{}]*\}', chunk):
                    obj_text = obj_match.group(0)
                    try:
                        obj_candidate = ast.literal_eval(obj_text)
                    except Exception:
                        skipped_count += 1
                        continue
                    if isinstance(obj_candidate, dict):
                        raw_data_list.append(obj_candidate)
                        recovered = True
                        recovered_count += 1
                    else:
                        skipped_count += 1
                if recovered:
                    log_fn = logger.warning if skipped_count else logger.info
                    log_fn(
                        f"数据分片自愈救回[第3轨-正则抠取]: "
                        f"n={recovered_count}, skipped={skipped_count}, chunk={chunk[:60]!r}"
                    )
                    continue
            # ── 第4轨：json_repair 容错修复兜底（仅在前三轨未产出数据时触发）──
            # 覆盖两类残差：断头 JSON（Token 物理截断补全）与寒暄文本包裹的结构化分片提取
            repaired = cls._json_repair_track(chunk)
            if repaired is not None:
                if isinstance(repaired, list):
                    raw_data_list.extend(repaired)
                else:
                    raw_data_list.append(repaired)
                logger.info(f"数据分片自愈救回[第4轨-json_repair]: chunk={chunk[:60]!r}")
                continue
            # 全轨失败告警：仅对声称含结构化内容的分片告警，纯状态文本（如 ok）静默跳过
            if "{" in chunk or "[" in chunk:
                logger.warning(f"数据分片解析彻底失败: chunk={chunk[:80]!r}")
        return raw_data_list

    # json_repair 会把 datetime(...) 函数调用整体折叠为字符串值，此正则用于按值还原 ISO 格式
    # （扁平装饰尾参段可吞掉 tzinfo 等参数；含 "(" 的嵌套尾参不还原，交由上层保留原始值；\)[,\s]*$ 兼容尾逗号残留）
    _DATETIME_CALL_VALUE_RE = re.compile(
        r'^\s*datetime\.datetime\((\d+),\s*(\d+),\s*(\d+)'
        r'(?:,\s*(\d+),\s*(\d+),\s*(\d+))?'
        r'(?:,\s*(\d+))?'
        r'(?:,[^)(]*)?\)[,\s]*$'
    )
    _DATE_CALL_VALUE_RE = re.compile(r'^\s*datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)[,\s]*$')

    @classmethod
    def _json_repair_track(cls, chunk: str) -> Any:
        """
        [第4轨] json_repair 容错修复兜底。
        契约：仅接受非空 dict/list；返回 None 表示本轨未救回，保留失败信号交由上层告警。
        依赖缺失（ImportError）时优雅降级为既有三轨行为。
        """
        try:
            import json_repair
        except ImportError:
            return None
        try:
            repaired = json_repair.loads(chunk)
        except Exception:
            return None
        if not isinstance(repaired, (dict, list)) or not repaired:
            return None
        return cls._restore_datetime_call_values(repaired)

    @classmethod
    def _restore_datetime_call_values(cls, obj: Any) -> Any:
        """json_repair 无法解析 datetime(...) 调用表达式，会将其折叠为字符串值；
        此处按值精确还原为 ISO 格式，杜绝脏字符串流入下游对账。"""
        if isinstance(obj, dict):
            return {k: cls._restore_datetime_call_values(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [cls._restore_datetime_call_values(v) for v in obj]
        if isinstance(obj, str):
            m = cls._DATETIME_CALL_VALUE_RE.match(obj)
            if m:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if m.group(4) is not None:
                    out = (
                        f"{year:04d}-{month:02d}-{day:02d} "
                        f"{int(m.group(4)):02d}:{int(m.group(5)):02d}:{int(m.group(6)):02d}"
                    )
                    if m.group(7) is not None:
                        out += f".{int(m.group(7)):06d}"
                    return out
                return f"{year:04d}-{month:02d}-{day:02d}"
            m = cls._DATE_CALL_VALUE_RE.match(obj)
            if m:
                return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return obj

    @classmethod
    def _coerce_iso_formats(cls, raw_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def _coerce(row):
            if not isinstance(row, dict):
                return row
            return {
                k: (v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v)
                for k, v in row.items()
            }
        return [_coerce(r) for r in raw_data_list] if isinstance(raw_data_list, list) else []
