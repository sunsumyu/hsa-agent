import pytest

def test_render_table_guidelines_fymx():
    from app.core.planning.table_guideline_renderer import render_table_guidelines
    hint = render_table_guidelines("fqz_fymx_test", "排查乡镇卫生院门诊费用")
    assert hint is not None
    assert "fqz_fymx_test" in hint
    assert "setl_time" in hint
    assert "fixmedins_name" in hint

def test_render_table_guidelines_yy_yd():
    from app.core.planning.table_guideline_renderer import render_table_guidelines
    hint = render_table_guidelines("fqz_all_yy_yd", "统计定点零售药店名录")
    assert hint is not None
    assert "fqz_all_yy_yd" in hint
    assert "fixmedins_code" in hint

def test_render_table_guidelines_admdvs():
    from app.core.planning.table_guideline_renderer import render_table_guidelines
    hint = render_table_guidelines("fqz_admdvs", "医保行政区划四级层级分布")
    assert hint is not None
    assert "fqz_admdvs" in hint
    assert "admdvs_lv" in hint

def test_render_table_guidelines_archetype_combined():
    from app.core.planning.table_guideline_renderer import render_table_guidelines
    hint = render_table_guidelines("fqz_gz_jzsj_all_ql", "对账排查就诊结算差异")
    assert hint is not None
    assert "fqz_gz_jzsj_all_ql" in hint
    # 结合了 Archetype 结构守卫提示
    assert "结构守卫" in hint or "资金对账" in hint

def test_render_table_guidelines_unknown():
    from app.core.planning.table_guideline_renderer import render_table_guidelines
    hint = render_table_guidelines("unknown_table", "日常咨询")
    assert hint is None
