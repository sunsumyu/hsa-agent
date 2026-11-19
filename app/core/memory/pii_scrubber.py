"""
app/core/memory/pii_scrubber.py
===============================
[Matt Pocock Deep Module] 医保审计个人隐私信息 (PII) 物理脱敏引擎

核心职责：
针对医保反欺诈审计全生命周期流转中的敏感隐私数据进行确定性、不可逆物理掩码：
1. 居民身份证号（15/18位）：保留前6位行政区划代码与后2位校验位；
2. 手机号码：保留前3位号段与后4位尾号；
3. 银行卡/医保金融卡（16-19位）：仅保留后4位；
4. 电子邮箱：掩码用户名部分；
5. 患者/医生姓名：掩码首字后的真实姓名。
"""

from __future__ import annotations

import re


class PIIScrubber:
    """PII 物理脱敏深模块"""

    def mask_sensitive_data(self, text: str) -> str:
        """对输入字符串执行不可逆隐私脱敏"""
        if not text:
            return ""

        # 1. 身份证号 (15/18位): 保留前6后2
        text = re.sub(
            r"\b\d{6}\d{8,11}[\dX]\b",
            lambda m: m.group()[:6] + "********" + m.group()[-2:],
            text,
        )

        # 2. 手机号: 保留前3后4
        text = re.sub(
            r"\b1[3-9]\d{9}\b",
            lambda m: m.group()[:3] + "****" + m.group()[-4:],
            text,
        )

        # 3. 银行卡/医保卡 (16-19位): 仅保留后4位
        text = re.sub(r"\b\d{12,15}(\d{4})\b", r"**** **** **** \1", text)

        # 4. 电子邮件: 掩码用户名
        text = re.sub(r"([a-zA-Z0-9_.+-])+[a-zA-Z0-9]@", r"****@", text)

        # 5. 疑似患者/医生姓名 (匹配“患者XXX”或“姓名：XXX”)
        text = re.sub(
            r"(患者|姓名|医生)[:：]\s*([\u4e00-\u9fa5]{1})[\u4e00-\u9fa5]{1,2}",
            r"\1: \2**",
            text,
        )

        return text


# 单例默认实例
pii_scrubber = PIIScrubber()
