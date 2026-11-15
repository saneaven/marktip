"""Readable carriers keep their bodies and ordinary surrounding block structure."""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value, *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def mark(type_, **attrs):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    return result


def node(type_, *, attrs=None, marks=()):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if marks:
        result["marks"] = list(marks)
    return result


def schema():
    return tm.Schema(nodes=[
        tm.NodeSpec("inlineMath", kind="inline", math="inline", body="latex",
                    attrs={"latex": tm.Attr(str)}),
        tm.NodeSpec("blockMath", kind="block", fence="math", math="display", body="latex",
                    attrs={"latex": tm.Attr(str)}),
    ])


def roundtrip(ast, markdown):
    declarations = schema()
    source = tm.from_dict(ast, schema=declarations, strict="exact")
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=declarations)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == markdown


@pytest.mark.parametrize("body", ("x^*", "x~~y", "[0,1)", "x]y"))
@pytest.mark.parametrize("shared, opening, closing", [
    (mark("italic"), "*", "*"),
    (mark("bold"), "**", "**"),
    (mark("strike"), "~~", "~~"),
    (mark("link", href="https://example.com"), "[", "](https://example.com)"),
])
def test_marked_math_with_mark_syntax_uses_its_tag_inside_shared_prose(body, shared, opening, closing):
    atom = node("inlineMath", attrs={"latex": body}, marks=[shared])
    ast = doc(p(text("optimal ", shared), atom, text(" is", shared)))
    roundtrip(ast, f'{opening}optimal <inlineMath latex="{body}"/> is{closing}')


@pytest.mark.parametrize("body", ("x^*", "x~~y", "[0,1)", "x]y"))
def test_unmarked_math_keeps_mark_syntax_raw_inside_dollars(body):
    roundtrip(doc(p(node("inlineMath", attrs={"latex": body}))), f"${body}$")


@pytest.mark.parametrize("body, encoded", [
    ("\tx", "&#9;x"),
    ("  \tx", "  &#9;x"),
    ("first\n\tx", "first&#10;&#9;x"),
])
def test_fence_body_with_an_indentation_tab_uses_its_tag(body, encoded):
    roundtrip(doc(node("blockMath", attrs={"latex": body})), f'<blockMath latex="{encoded}"/>')


def test_fence_body_with_a_nonleading_tab_keeps_the_fence():
    roundtrip(doc(node("blockMath", attrs={"latex": "x\ty"})), "```math\nx\ty\n```")


@pytest.mark.parametrize("following, type_", [
    ("after", "paragraph"),
    ("| h |\n| --- |", "table"),
    ("<!-- after -->", "htmlBlock"),
])
def test_fence_followed_by_an_ordinary_block_keeps_a_list_tight(following, type_):
    declarations = schema()
    source = "- before\n  ```math\n  x\n  ```\n  " + following.replace("\n", "\n  ")
    if type_ != "htmlBlock":
        source += "\n- next"
    parsed = tm.from_markdown(source, schema=declarations)
    first = parsed.to_dict()["content"][0]
    assert first["attrs"]["tight"] is True
    assert [child["type"] for child in first["content"][0]["content"]] == [
        "paragraph", "blockMath", type_,
    ]
    if type_ != "htmlBlock":
        assert first["content"][1] == {"type": "listItem", "content": [p(text("next"))]}
    else:
        assert len(first["content"]) == 1
    written = parsed.to_markdown(canonical=True)
    assert "\n  ```\n  " + following.split("\n")[0] in written
    reparsed = tm.from_markdown(written, schema=declarations)
    assert reparsed.to_dict() == parsed.to_dict()
    assert reparsed.to_markdown(canonical=True) == written


@pytest.mark.parametrize("source, body", [
    ("$$ x $$", "x"),
    ("$$\nx\n$$", "x"),
    ("$$ \t x \t $$", "x"),
    ("$$\nx\ny\n$$", "x y"),
])
def test_display_math_trims_its_boundary_whitespace_and_normalizes_internal_line_breaks(source, body):
    declarations = schema()
    parsed = tm.from_markdown(source, schema=declarations)
    expected = doc(node("blockMath", attrs={"latex": body}))
    assert parsed.to_dict() == expected
    written = f"```math\n{body}\n```"
    assert parsed.to_markdown(canonical=True) == written
    assert tm.from_markdown(written, schema=declarations).to_dict() == expected


@pytest.mark.parametrize("source, body", [("$ x $", " x "), ("$x\ny$", "x y")])
def test_inline_math_keeps_boundary_spaces_and_normalizes_line_breaks(source, body):
    declarations = schema()
    parsed = tm.from_markdown(source, schema=declarations)
    expected = doc(p(node("inlineMath", attrs={"latex": body})))
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == f"${body}$"
    assert tm.from_markdown(parsed.to_markdown(canonical=True), schema=declarations).to_dict() == expected


@pytest.mark.parametrize("info", ("math title", "math title with spaces"))
def test_fence_reader_uses_the_first_word_of_effective_info(info):
    declarations = schema()
    parsed = tm.from_markdown(f"```{info}\nx\n```", schema=declarations)
    expected = doc(node("blockMath", attrs={"latex": "x"}))
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == "```math\nx\n```"
    assert tm.from_markdown(parsed.to_markdown(canonical=True), schema=declarations).to_dict() == expected
