"""
tests/unit/test_law_rag_tools.py
================================
法规库检索工具的单元契约测试（mock HTTP，零网络依赖）：
覆盖命中渲染格式、分类过滤注入、空结果兜底、无效分类与连接失败降级。
"""

import json

import pytest

from app.skills import law_rag_tools


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """记录请求体并回放预设响应的最小 AsyncClient 替身"""

    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.last_body = None

    async def post(self, url, json=None, **kwargs):
        self.last_body = json
        if self.error:
            raise self.error
        return _FakeResponse(self.payload)


def _hit(source="法律/中华人民共和国个人信息保护法_20210820_x.pdf", page=8, text="敏感个人信息处理应当取得个人的单独同意。"):
    return {"text": text, "score": 0.42, "source": source, "page_num": page,
            "page_num_accurate": True, "chunk_idx": 3}


@pytest.mark.unit
async def test_report_renders_source_page_and_content(monkeypatch):
    fake = _FakeClient(payload={"text_results": [_hit()], "table_results": []})
    monkeypatch.setattr(law_rag_tools, "_client", lambda: fake)

    report = await law_rag_tools.query_law_database.ainvoke({"query": "敏感个人信息 同意"})

    assert "【法规库检索报告" in report
    assert "[来源: 法律/中华人民共和国个人信息保护法_20210820_x.pdf | 第8页]" in report
    assert "单独同意" in report
    assert fake.last_body.get("source") is None  # 未传分类时请求体不带 source 过滤
    assert fake.last_body["mode"] == "hybrid"


@pytest.mark.unit
async def test_category_filter_injects_prefix(monkeypatch):
    fake = _FakeClient(payload={"text_results": [], "table_results": []})
    monkeypatch.setattr(law_rag_tools, "_client", lambda: fake)

    await law_rag_tools.query_law_database.ainvoke({"query": "骗保 处罚", "category": "司法解释"})

    assert fake.last_body["source"] == "司法解释/"


@pytest.mark.unit
async def test_invalid_category_rejected_without_http_call(monkeypatch):
    called = {"n": 0}

    class _NeverCalled(_FakeClient):
        async def post(self, *a, **kw):
            called["n"] += 1
            raise AssertionError("无效分类不应发起 HTTP 请求")

    monkeypatch.setattr(law_rag_tools, "_client", lambda: _NeverCalled())
    report = await law_rag_tools.query_law_database.ainvoke({"query": "x", "category": "部门规章"})

    assert "无效分类" in report and "部门规章" in report
    assert called["n"] == 0


@pytest.mark.unit
async def test_empty_results_fallback(monkeypatch):
    fake = _FakeClient(payload={"text_results": [], "table_results": []})
    monkeypatch.setattr(law_rag_tools, "_client", lambda: fake)

    report = await law_rag_tools.query_law_database.ainvoke({"query": "不存在的条文"})

    assert "未在法规库中找到相关条文" in report
    assert "司法解释" in report  # 兜底文案列出可用分类


@pytest.mark.unit
async def test_connection_failure_degrades_gracefully(monkeypatch):
    fake = _FakeClient(error=ConnectionError("All connection attempts failed"))
    monkeypatch.setattr(law_rag_tools, "_client", lambda: fake)

    report = await law_rag_tools.query_law_database.ainvoke({"query": "骗保"})

    assert "检索服务不可达" in report
    assert "LAW_RAG_BASE_URL" in report or "python.rpc_server.server" in report


@pytest.mark.unit
async def test_long_content_truncated(monkeypatch):
    long_text = "第X条 " + "很长的条文内容" * 200  # >600 字
    fake = _FakeClient(payload={"text_results": [_hit(text=long_text)], "table_results": []})
    monkeypatch.setattr(law_rag_tools, "_client", lambda: fake)

    report = await law_rag_tools.query_law_database.ainvoke({"query": "长条文"})

    assert "…" in report  # 截断标记
    assert report.count("很长的条文内容") * len("很长的条文内容") < len(long_text)  # 未全文回显
