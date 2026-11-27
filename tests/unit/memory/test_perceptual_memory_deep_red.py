"""
tests/unit/memory/test_perceptual_memory_deep_red.py
===================================================
[Matt Pocock Deep Module Red Test] 多模态感知记忆 (Perceptual Memory) 架构与优雅降级测试
涵盖：
1. 感知模型延迟加载与优雅降级 (CLIP 加载失败自动切回纯文本模式)
2. 多模态资产解析与 Markdown 转换 (_convert_to_markdown)
3. 视觉凭证特征提取与向量入库 (add_image via CLIP vs 纯文本降级)
4. 双路径混合召回 (视觉语义对齐文搜图 vs 元数据降级检索)
5. 提示词格式化契约 (format_perceptual_for_prompt)
"""

import os
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.memory.base import MemoryItem
from app.core.memory.types.perceptual import PerceptualMemory


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.add = AsyncMock()
    storage.search = AsyncMock()
    return storage


def test_perceptual_memory_model_init_fallback(mock_storage, monkeypatch):
    """验证当多模态环境缺失或网络异常时，感知记忆优雅降级至纯文本模式而不中断"""
    pm = PerceptualMemory(storage=mock_storage)
    assert pm._clip_model is None
    assert pm._init_failed is False

    # 模拟 SentenceTransformer 导入或加载异常
    import sys
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    pm._init_models()
    assert pm._clip_model is None
    assert pm._init_failed is True

    # 再次触发应短路跳过
    pm._init_models()
    assert pm._init_failed is True


def test_perceptual_memory_convert_to_markdown(mock_storage, tmp_path):
    """验证多模态与文档资产转换 Markdown 逻辑"""
    pm = PerceptualMemory(storage=mock_storage)

    # 1. 不存在的文件 -> 空字符串
    assert pm._convert_to_markdown(str(tmp_path / "not_exist.txt")) == ""

    # 2. 图片扩展名 -> 空字符串 (留给 CLIP 视觉特征处理)
    dummy_img = tmp_path / "receipt.png"
    dummy_img.write_bytes(b"dummy_png_bytes")
    assert pm._convert_to_markdown(str(dummy_img)) == ""

    # 3. 纯文本 / Markdown 文件 -> 读取文本内容
    doc_file = tmp_path / "medical_guideline.txt"
    doc_file.write_text("医保住院审核规范：分解住院判定准则", encoding="utf-8")
    parsed_content = pm._convert_to_markdown(str(doc_file))
    assert "医保住院审核规范" in parsed_content


@pytest.mark.asyncio
async def test_perceptual_memory_add_image_with_clip(mock_storage, tmp_path, monkeypatch):
    """验证当 CLIP 模型可用时，图片资产通过视觉 Embedding 引擎存入向量库"""
    pm = PerceptualMemory(storage=mock_storage)

    # 模拟 CLIP 模型可用
    mock_clip = MagicMock()
    mock_clip.encode.return_value = [[0.1, 0.2, 0.3]]
    pm._clip_model = mock_clip

    # 创建一个临时图片文件
    img_file = tmp_path / "test_invoice.jpg"
    img_file.write_bytes(b"fake_jpg")

    # 模拟 PIL.Image.open
    mock_pil = MagicMock()
    mock_img_obj = MagicMock()
    mock_pil.open.return_value = mock_img_obj
    import sys
    monkeypatch.setitem(sys.modules, "PIL", MagicMock(Image=mock_pil))
    monkeypatch.setitem(sys.modules, "PIL.Image", mock_pil)

    await pm.add_image(
        image_path=str(img_file),
        description="住院发票违规收费凭单",
        importance=0.8,
        invoice_id="INV-9988"
    )

    # 验证向 storage.add 提交了一项 MemoryItem，并且携带了 ImageEmbeddingWrapper
    mock_storage.add.assert_awaited_once()
    call_args = mock_storage.add.call_args
    items = call_args[0][0]
    kwargs = call_args[1]

    assert len(items) == 1
    assert items[0].memory_type == "perceptual"
    assert items[0].metadata["modality"] == "image"
    assert items[0].metadata["file_path"] == str(img_file)
    assert items[0].metadata["invoice_id"] == "INV-9988"
    assert "embeddings_engine" in kwargs
    # 验证 embeddings_engine 调用了 CLIP 编码
    wrapper = kwargs["embeddings_engine"]
    assert wrapper.embed_documents(["any"]) == [[0.1, 0.2, 0.3]]


@pytest.mark.asyncio
async def test_perceptual_memory_add_document_fallback(mock_storage, tmp_path):
    """验证当录入非图片文档时，提取文档内容并通过通用文本向量写入"""
    pm = PerceptualMemory(storage=mock_storage)
    pm._init_failed = True  # 强制纯文本模式

    doc_file = tmp_path / "audit_case.md"
    doc_file.write_text("# 案例记录\n涉嫌伪造就诊记录单据", encoding="utf-8")

    await pm.add_image(
        image_path=str(doc_file),
        description="涉案凭证附件",
        importance=0.9
    )

    mock_storage.add.assert_awaited_once()
    items = mock_storage.add.call_args[0][0]
    assert len(items) == 1
    assert items[0].metadata["modality"] == "document"
    assert items[0].metadata["has_text"] is True
    assert "涉嫌伪造就诊记录单据" in items[0].content


@pytest.mark.asyncio
async def test_perceptual_memory_recall_clip_and_fallback(mock_storage):
    """验证感知召回的双路径：视觉跨模态对齐 (文搜图) vs 降级元数据文本检索"""
    pm = PerceptualMemory(storage=mock_storage)

    # 路径 A: CLIP 模型存在，执行文搜图 (向量对齐检索)
    mock_clip = MagicMock()
    mock_clip.encode.return_value = MagicMock(tolist=lambda: [0.5, 0.6, 0.7])
    pm._clip_model = mock_clip

    await pm.recall(query="门诊高额发票凭证", limit=3, tenant_id="hsa_test")
    mock_storage.search.assert_awaited_once_with(
        limit=3,
        tenant_id="hsa_test",
        query_vector=[0.5, 0.6, 0.7]
    )

    # 路径 B: 降级模式 (无 CLIP 模型)，执行元数据文本检索
    pm._clip_model = None
    pm._init_failed = True
    mock_storage.search.reset_mock()

    await pm.recall(query="超量开药处方单", limit=5, tenant_id="hsa_test")
    mock_storage.search.assert_awaited_once_with(
        query="超量开药处方单",
        limit=5,
        tenant_id="hsa_test"
    )


def test_perceptual_memory_format_perceptual_for_prompt(mock_storage):
    """验证感知记忆转换为 Agent Prompt 的契约规范"""
    pm = PerceptualMemory(storage=mock_storage)

    # 1. 空结果
    assert pm.format_perceptual_for_prompt([]) == "未找到相关的感知凭证（如图像、发票截图）。"

    # 2. 存在凭证条目
    items = [
        MemoryItem(
            content="发票扫描件",
            memory_type="perceptual",
            metadata={"description": "某医院男科结算单据", "file_path": "data/invoices/inv_01.jpg"}
        ),
        MemoryItem(
            content="处方笺照片",
            memory_type="perceptual",
            metadata={"description": "重复开具头孢曲松处方笺", "file_path": "data/invoices/inv_02.png"}
        )
    ]

    formatted = pm.format_perceptual_for_prompt(items)
    assert "【关联的感知凭证与视觉证据】" in formatted
    assert "1. 凭证说明: 某医院男科结算单据 (路径: data/invoices/inv_01.jpg)" in formatted
    assert "2. 凭证说明: 重复开具头孢曲松处方笺 (路径: data/invoices/inv_02.png)" in formatted
