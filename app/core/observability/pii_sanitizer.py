# -*- coding: utf-8 -*-
"""
app/core/observability/pii_sanitizer.py
=======================================
[安全门禁] 医保审计数据合规脱敏器 (PIISanitizer)
离开本地进程前物理脱敏所有参保人隐私数据 (身份证、手机号、医保卡/社保卡) 及系统密钥。
"""

import re
from typing import Any

RE_ID_CARD = re.compile(
    r"(?<!\d)([1-9]\d{5})(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(\d{3}[\dXx])(?!\d)"
)
RE_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
RE_CARD_NO = re.compile(r"(?<!\d)(\d{6})\d{6,12}(\d{4})(?!\d)")
SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "authorization"}


class PIISanitizer:
    """[安全门禁] 医保审计数据合规脱敏器"""

    @classmethod
    def sanitize(cls, val: Any) -> Any:
        """深度递归脱敏 dict, list, tuple, set, str 数据"""
        if isinstance(val, str):
            val = RE_ID_CARD.sub(r"\1**********\2", val)
            val = RE_PHONE.sub(r"\1****\2", val)
            return RE_CARD_NO.sub(r"\1******\2", val)
        elif isinstance(val, dict):
            res = {}
            for k, v in val.items():
                is_sensitive = any(s in str(k).lower() for s in SENSITIVE_KEYS)
                if is_sensitive and not isinstance(v, (dict, list, tuple, set)):
                    res[k] = "[REDACTED]"
                elif is_sensitive and isinstance(v, (list, tuple, set)):
                    redacted_items = [
                        cls.sanitize(item) if isinstance(item, (dict, list, tuple, set)) else "[REDACTED]"
                        for item in v
                    ]
                    if isinstance(v, tuple):
                        res[k] = tuple(redacted_items)
                    elif isinstance(v, set):
                        res[k] = set(redacted_items)
                    else:
                        res[k] = redacted_items
                else:
                    res[k] = cls.sanitize(v)
            return res
        elif isinstance(val, list):
            return [cls.sanitize(item) for item in val]
        elif isinstance(val, tuple):
            return tuple(cls.sanitize(item) for item in val)
        elif isinstance(val, set):
            return {cls.sanitize(item) for item in val}
        return val
