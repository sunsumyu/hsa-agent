from app.core.guardrails.citation_guardrail import enforce_citation_grounding


def _sample_ledger():
    return [
        {
            "citation_id": "law_11223344",
            "source_type": "law_rag",
            "source_doc": "行政法规/医疗保障基金使用监督管理条例.pdf",
            "section_path": "",
            "page_num": 5,
            "law_title": "医疗保障基金使用监督管理条例",
            "article_num": "第十五条",
            "snippet": "第十五条 定点医药机构不得分解住院、挂床住院。",
            "content_hash": "aabbccddeeff",
        }
    ]


def test_expands_valid_cite_id_and_strips_fabricated_cite_id():
    text = "依据 [CITE:law_11223344] 构成违规，另参考 [CITE:law_deadbeef]。"
    res = enforce_citation_grounding(text, _sample_ledger(), strict=True)
    assert "《医疗保障基金使用监督管理条例》第十五条" in res.sanitized_text
    assert "law_11223344" in res.verified_ids
    assert "law_deadbeef" not in res.sanitized_text
    assert any("law_deadbeef" in b for b in res.blocked_citations)
    assert res.passed is False


def test_allows_grounded_freeform_citation_and_blocks_hallucinated_statute():
    text = (
        "本案违反《医疗保障基金使用监督管理条例》第十五条，"
        "同时涉嫌触犯《中华人民共和国医保反欺诈特别法》第九十九条。"
    )
    res = enforce_citation_grounding(text, _sample_ledger(), strict=True)
    assert "《医疗保障基金使用监督管理条例》第十五条" in res.sanitized_text
    assert "《中华人民共和国医保反欺诈特别法》第九十九条" not in res.sanitized_text
    assert "[已拦截未核验法规引用]" in res.sanitized_text
    assert any("医保反欺诈特别法" in b for b in res.blocked_citations)


def test_blocks_hallucinated_article_number_on_real_law():
    text = "本案依据《医疗保障基金使用监督管理条例》第八十八条处罚。"
    res = enforce_citation_grounding(text, _sample_ledger(), strict=True)
    assert "第八十八条" not in res.sanitized_text
    assert len(res.blocked_citations) == 1


def test_cite_expansion_never_self_blocks_when_law_title_empty_with_source_doc_fallback():
    ledger = [
        {
            "citation_id": "law_55667788",
            "source_type": "law_rag",
            "source_doc": "行政法规/医疗保障基金使用监督管理条例.pdf",
            "section_path": "",
            "page_num": 5,
            "law_title": "",
            "article_num": "第十五条",
            "snippet": "定点医药机构不得分解住院、挂床住院。",
            "content_hash": "112233445566",
        },
        {
            "citation_id": "rag_99aabbcc",
            "source_type": "vector_rag",
            "source_doc": "地方文件/医保飞行检查操作指引.md",
            "section_path": "第三章",
            "page_num": None,
            "law_title": "",
            "article_num": "",
            "snippet": "核查住院病历与收费清单一致性。",
            "content_hash": "665544332211",
        },
    ]
    text = "依据 [CITE:law_55667788] 及 [CITE:rag_99aabbcc] 开展核查。"
    res = enforce_citation_grounding(text, ledger, strict=True)
    assert res.passed is True
    assert res.blocked_citations == []
    assert res.verified_ids == ["law_55667788", "rag_99aabbcc"]
    assert "《医疗保障基金使用监督管理条例》第十五条" in res.sanitized_text
    assert "《医保飞行检查操作指引》" in res.sanitized_text
    assert "[已拦截未核验法规引用]" not in res.sanitized_text


def test_non_strict_mode_preserves_unverified_freeform_citation_and_records_block():
    text = "依据《未核验地方规定》第三条处理。"
    res = enforce_citation_grounding(text, _sample_ledger(), strict=False)
    assert res.passed is False
    assert "《未核验地方规定》第三条" in res.sanitized_text
    assert "[已拦截未核验法规引用]" not in res.sanitized_text
    assert res.blocked_citations == ["《未核验地方规定》第三条"]


def test_empty_text_passes_cleanly():
    res = enforce_citation_grounding("", _sample_ledger(), strict=True)
    assert res.passed is True
    assert res.sanitized_text == ""
    assert res.verified_ids == []
    assert res.blocked_citations == []
