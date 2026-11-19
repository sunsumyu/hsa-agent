"""
tests/unit/core/test_api_response_envelope_red.py
=================================================
针对统一响应信封 ApiResponse 的单元测试：
1. ApiResponse.success 标准成功载荷构造
2. ApiResponse.fail 标准失败载荷构造
3. Generic 泛型类型支持与 Pydantic 校验序列化
4. 与既有系统协议的双向对齐兼容 (ok, message, error, data)
5. 错误与异常自动转化为标准信封 (from_exception)
"""

import pytest
from pydantic import BaseModel
from app.core.schemas import ApiResponse


class SamplePayload(BaseModel):
    user_id: str
    amount: float


def test_api_response_success_factory():
    resp = ApiResponse.success(data={"token": "abc123xyz"}, message="登录成功")
    assert resp.ok is True
    assert resp.code == 200
    assert resp.message == "登录成功"
    assert resp.data == {"token": "abc123xyz"}
    assert resp.error is None

    # 导出字典结构验证
    d = resp.model_dump()
    assert d["ok"] is True
    assert d["data"]["token"] == "abc123xyz"


def test_api_response_fail_factory():
    resp = ApiResponse.fail(error="参数非法: threshold 不能为负数", code=400)
    assert resp.ok is False
    assert resp.code == 400
    assert "threshold 不能为负数" in resp.error
    assert resp.data is None


def test_api_response_generic_model():
    payload = SamplePayload(user_id="U1001", amount=999.5)
    resp = ApiResponse[SamplePayload].success(data=payload)

    assert resp.ok is True
    assert resp.data.user_id == "U1001"
    assert resp.data.amount == 999.5


def test_api_response_from_exception():
    err = ValueError("不支持的淘汰策略: dummy")
    resp = ApiResponse.from_exception(err, code=400)

    assert resp.ok is False
    assert resp.code == 400
    assert "不支持的淘汰策略" in resp.error
    assert resp.message == str(err)
