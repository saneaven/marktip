import pytest

import marktip as tm


def marked_texts(markdown, mark_type, *, cjk_friendly=True):
    content = tm.from_markdown(markdown, cjk_friendly=cjk_friendly).to_dict()["content"][0]["content"]
    return [node["text"] for node in content if {"type": mark_type} in node.get("marks", [])]


@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
@pytest.mark.parametrize("prefix,suffix", [("", "a"), ("a", ""), ("a", "a"), ("", "을")])
@pytest.mark.parametrize("value", ["《제목》", "「約束」"])
def test_cjk_punctuation_adjoins_latin_or_hangul(delimiter, mark_type, prefix, suffix, value):
    markdown = prefix + delimiter + value + delimiter + suffix
    assert marked_texts(markdown, mark_type) == [value]
    if prefix == "a" or suffix == "a":
        assert marked_texts(markdown, mark_type, cjk_friendly=False) == []


@pytest.mark.parametrize("value", ["１", "₩", "ｶ", "ᅡ", "〰", "〽", "㊗", "㊙", "🈂", "🈷", "𠀀"])
@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
def test_unicode_width_and_hangul_script_define_cjk(value, delimiter, mark_type):
    assert marked_texts("a" + delimiter + value + delimiter + "a", mark_type) == [value]
    assert marked_texts(value + delimiter + '"제목"' + delimiter + value, mark_type) == ['"제목"']


@pytest.mark.parametrize("value", ["😀", "⌚", "🈁", "©", "☀"])
@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
def test_default_emoji_and_non_cjk_symbols_do_not_relax_flanking(value, delimiter, mark_type):
    assert marked_texts("a" + delimiter + value + delimiter + "a", mark_type) == []


@pytest.mark.parametrize("selector", ["\ufe00", "\ufe01", "\ufe0e", "\U000e0100", "\U000e01ef"])
@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
def test_cjk_variation_sequence_before_opener(selector, delimiter, mark_type):
    markdown = "漢" + selector + delimiter + '"제목"' + delimiter + "１"
    assert marked_texts(markdown, mark_type) == ['"제목"']
    assert marked_texts(markdown, mark_type, cjk_friendly=False) == []


@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
def test_emoji_selector_does_not_form_a_cjk_sequence(delimiter, mark_type):
    assert marked_texts("漢\ufe0f" + delimiter + '"제목"' + delimiter + "１", mark_type) == []


@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
def test_non_cjk_punctuation_sequence_still_blocks_closing(delimiter, mark_type):
    assert marked_texts("a" + delimiter + "x.\ufe00" + delimiter + "b", mark_type) == []
    assert marked_texts("a" + delimiter + "x.\ufe0f" + delimiter + "b", mark_type) == ["x.\ufe0f"]


@pytest.mark.parametrize("delimiter,mark_type", [("**", "bold"), ("*", "italic"), ("~~", "strike")])
@pytest.mark.parametrize("value", ["x.\ufe00", "x”\ufe00"])
def test_punctuation_sequence_can_close_before_cjk(delimiter, mark_type, value):
    assert marked_texts("a" + delimiter + value + delimiter + "字", mark_type) == [value]


@pytest.mark.parametrize("quote", ["‘", "’", "“", "”"])
def test_fullwidth_ambiguous_punctuation_sequence(quote):
    value = "제목" + quote + "\ufe01"
    assert marked_texts("a**" + value + "**a", "bold") == [value]
    assert marked_texts("a**제목" + quote + "\ufe00**a", "bold") == []


@pytest.mark.parametrize("delimiter", ["_", "__"])
@pytest.mark.parametrize("prefix,suffix", [("", "을"), ("a", ""), ("a", "a")])
def test_underscores_retain_commonmark_intraword_restrictions(delimiter, prefix, suffix):
    markdown = prefix + delimiter + "《제목》" + delimiter + suffix
    assert tm.from_markdown(markdown, cjk_friendly=True).to_dict()["content"][0]["content"] == [
        {"type": "text", "text": markdown}
    ]


@pytest.mark.parametrize("delimiter,mark_type", [("_", "italic"), ("__", "bold")])
def test_underscores_accept_preceding_punctuation_sequence(delimiter, mark_type):
    assert marked_texts("a.\ufe00" + delimiter + "제목" + delimiter + "!", mark_type) == ["제목"]
    assert marked_texts("(" + delimiter + "《제목》" + delimiter + ")", mark_type) == ["《제목》"]


@pytest.mark.parametrize("mark_type", ["bold", "italic", "strike"])
def test_editor_mark_on_cjk_punctuation_roundtrips_before_latin(mark_type):
    ast = {
        "type": "doc",
        "content": [{
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "《제목》", "marks": [{"type": mark_type}]},
                {"type": "text", "text": "a"},
            ],
        }],
    }
    markdown = tm.from_dict(ast, cjk_friendly=True).to_markdown(canonical=True)
    assert tm.from_markdown(markdown, cjk_friendly=True).to_dict() == ast
