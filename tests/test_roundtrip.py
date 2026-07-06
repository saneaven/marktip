import pytest

import marktip as tm


def assert_stable(markdown: str):
    doc = tm.from_markdown(markdown)
    serialized = doc.to_markdown()
    assert tm.from_markdown(serialized).to_dict() == doc.to_dict()


def test_roundtrip_core_blocks_and_marks():
    assert_stable(
        "# Title\n\n"
        "A **bold** and *italic* paragraph with `code` and ~~strike~~.\n\n"
        "> quoted\n\n"
        "- one\n"
        "- two\n\n"
        "1. first\n"
        "2. second\n"
    )


def test_roundtrip_gfm_table_task_list_and_code():
    assert_stable(
        "- [x] done\n"
        "- [ ] todo\n\n"
        "| A | B |\n"
        "| :- | -: |\n"
        "| x | y |\n\n"
        "```python\n"
        "print('ok')\n"
        "```\n"
    )


def test_roundtrip_multi_block_list_items_and_loose_lists():
    assert_stable("- first\n\n  second\n")
    assert_stable("- a\n\n- b\n")


def test_roundtrip_hard_break_inside_marks():
    assert_stable("**a\\\nb**")
    assert_stable("[a\\\nb](https://example.com)")


def test_roundtrip_block_markers_escaped_in_text():
    assert_stable("\\- not a list")
    assert_stable("\\> not a quote")
    assert_stable("1\\. not ordered")


def test_roundtrip_ordered_task_list():
    assert_stable("1. [x] done\n2. [ ] todo\n")


def test_roundtrip_large_and_deep_smoke():
    nested = "- root\n  - child\n    - grandchild\n"
    large = "\n".join(f"Paragraph {i} with **bold** text." for i in range(200))
    assert_stable(nested + "\n" + large)


# ─────────────────────────────────────────────────────────────────────────
# Adversarial round-trip regressions.
#
# The tests above check md -> AST -> md -> AST stability for markdown
# input. The tests below cover the two remaining invariants of a canonical
# pipeline:
#
#   1. AST identity:   from_dict -> to_markdown -> from_markdown == input
#      (an editor document survives serialization; no mark silently drops)
#   2. Byte idempotence: normalize(normalize(md)) == normalize(md)
#      (re-saving an unchanged document never changes bytes)
#
# CJK text next to emphasis delimiters is not recognized by standard
# CommonMark flanking rules; those cases round-trip only under the
# non-standard `cjk_friendly=True` parsing extension, so the tests pass the
# flag explicitly. Whitespace touching an emphasis boundary has no valid
# markdown representation at all; the serializer expels it outside the
# delimiters, and the tests assert that normalization.

# ── helpers ──────────────────────────────────────────────────────────────


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def hard_break(*marks):
    node = {"type": "hardBreak"}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def normalize(md):
    return tm.from_markdown(md).to_markdown()


def assert_ast_roundtrip(ast, cjk_friendly=False):
    md = tm.from_dict(ast).to_markdown()
    back = tm.from_markdown(md, cjk_friendly=cjk_friendly).to_dict()
    assert back == ast, f"serialized markdown: {md!r}"


# ── regression guards: currently passing, must stay green ───────────────


def test_plain_cjk_bold():
    assert_ast_roundtrip(doc(p(text("볼드", "bold"), text("입니다"))))


def test_paren_ordered_marker_escaped():
    # '1)' is a valid CommonMark ordered-list marker; global paren escaping
    # currently prevents the reparse. Guards against relaxing escape_inline.
    assert_ast_roundtrip(doc(p(text("1) 항목처럼 보이는 문장"))))


def test_dot_ordered_marker_escaped():
    assert_ast_roundtrip(doc(p(text("2026. 연간 회고"))))


def test_thematic_break_lookalike():
    assert_ast_roundtrip(doc(p(text("---"))))


def test_setext_lookalike_after_hard_break():
    assert_ast_roundtrip(doc(p(text("제목처럼"), hard_break(), text("==="))))


def test_code_mark_with_backticks():
    assert_ast_roundtrip(doc(p(text("a`b", "code"))))


def test_hard_break_inside_bold():
    assert_ast_roundtrip(
        doc(p(text("첫 줄", "bold"), hard_break("bold"), text("둘째 줄", "bold")))
    )


# ── AST identity: CJK-adjacent emphasis (needs cjk_friendly parsing) ─────


def test_bold_before_cjk_particle():
    # Standard flanking rejects `)**은` (punctuation before, letter after);
    # the cjk_friendly extension accepts it.
    assert_ast_roundtrip(
        doc(p(text("마크다운(Markdown)", "bold"), text("은 표준이다"))),
        cjk_friendly=True,
    )


def test_italic_ending_with_fullwidth_stop():
    # `*강조。*다음` — U+3002 is punctuation, '다' is a CJK letter.
    assert_ast_roundtrip(
        doc(p(text("강조。", "italic"), text("다음 문장"))), cjk_friendly=True
    )


def test_bold_quoted_word_before_particle():
    # `**"인용"**라고` — '"' before the closing delimiter, CJK letter after.
    assert_ast_roundtrip(
        doc(p(text('"인용"', "bold"), text("라고 말했다"))), cjk_friendly=True
    )


def test_strike_before_cjk_particle():
    # `~~삭제~~은` — the strikethrough closer is also blocked by standard rules.
    assert_ast_roundtrip(
        doc(p(text("삭제", "strike"), text("은 취소선"))), cjk_friendly=True
    )


def test_cjk_relaxation_is_opt_in():
    # Default parsing must stay exactly GFM/CommonMark: the emphasis does not
    # close, so the delimiters remain literal text.
    md = tm.from_dict(
        doc(p(text("마크다운(Markdown)", "bold"), text("은 표준이다")))
    ).to_markdown()
    reparsed = tm.from_markdown(md).to_dict()
    assert reparsed["content"][0]["content"][0]["text"].startswith("**")


# ── boundary whitespace: expelled outside the delimiters ─────────────────
# Whitespace touching an emphasis delimiter has no valid markdown
# representation, so the serializer moves it outside the marks
# (cf. prosemirror-markdown expelEnclosingWhitespace). Text content and
# rendering are unchanged; only the space's mark membership normalizes.


def test_trailing_space_inside_bold_is_expelled():
    ast = doc(p(text("굵게 ", "bold"), text("이후 텍스트")))
    md = tm.from_dict(ast).to_markdown()
    assert md == "**굵게** 이후 텍스트"
    assert tm.from_markdown(md).to_dict() == doc(
        p(text("굵게", "bold"), text(" 이후 텍스트"))
    )


def test_leading_space_inside_bold_is_expelled():
    ast = doc(p(text("앞"), text(" 굵게", "bold")))
    md = tm.from_dict(ast).to_markdown()
    assert md == "앞 **굵게**"
    assert tm.from_markdown(md).to_dict() == doc(p(text("앞 "), text("굵게", "bold")))


# ── mark runs: shared marks stay open across run boundaries ──────────────


def test_adjacent_bold_to_bold_italic():
    # Serializes to `**a*b***`: the shared bold stays open, so the reparse
    # restores the exact mark order.
    assert_ast_roundtrip(doc(p(text("a", "bold"), text("b", "bold", "italic"))))


# ── idempotence: normalize twice == normalize once ───────────────────────

IDEMPOTENCE_CORPUS = [
    "**a*****b***",
    "これは**私のやりたかったこと。**だからするの。",
    "**마크다운(Markdown)**은 표준이다",
    "**굵게 **이후",
    "\\*리터럴\\* 별표",
    "- 항목 하나\n- 항목 둘",
    "1. one\n1. two",
    "> 인용\n>\n> 두 문단",
    "`code` 와 **bold** 혼합",
    "a  \nb",
]


@pytest.mark.parametrize("md", IDEMPOTENCE_CORPUS)
def test_normalize_is_idempotent(md):
    once = normalize(md)
    assert normalize(once) == once, f"first pass produced: {once!r}"