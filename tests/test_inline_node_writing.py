"""Writer rules for inline-container context and mark barriers."""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def text(value, *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def wrap(*children, marks=()):
    result = {"type": "wrap", "content": list(children)}
    if marks:
        result["marks"] = list(marks)
    return result


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("level", ("off", "content", "exact"))
@pytest.mark.parametrize("children", (
    [text("a"), {"type": "hardBreak"}, text("b")],
    [text("a\nb")],
))
def test_heading_container_preserves_the_core_break_and_newline_normalization(html, level, children):
    schema = tm.Schema(nodes=[tm.NodeSpec("wrap", kind="inline", content="inline*")])
    ast = doc({"type": "heading", "attrs": {"level": 2}, "content": [wrap(*children)]})
    source = tm.from_dict(ast, schema=schema, strict=level)
    markdown = "## <wrap>a b</wrap>"
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    expected = doc({"type": "heading", "attrs": {"level": 2}, "content": [wrap(text("a b"))]})
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markdown


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("mark, before, inside, after", (
    ({"type": "bold"}, "**a**", "**b**", "**c**"),
    ({"type": "italic"}, "*a*", "*b*", "*c*"),
    ({"type": "strike"}, "~~a~~", "~~b~~", "~~c~~"),
    ({"type": "code"}, "`a`", "`b`", "`c`"),
    ({"type": "link", "attrs": {"href": "https://example.com"}},
     "[a](https://example.com)", "[b](https://example.com)", "[c](https://example.com)"),
    ({"type": "underline"}, "<u>a</u>", "<u>b</u>", "<u>c</u>"),
))
def test_off_ignores_container_own_marks_and_keeps_the_container_as_a_barrier(html, mark, before, inside, after):
    schema = tm.Schema(nodes=[tm.NodeSpec("wrap", kind="inline", content="inline*")],
                       marks=[tm.MarkSpec("underline", tag="u")])
    children = [text("a", mark), wrap(text("b", mark), marks=[mark]), text("c", mark)]
    source = tm.from_dict(doc({"type": "paragraph", "content": children}), schema=schema, strict="off")
    markdown = before + "<wrap>" + inside + "</wrap>" + after
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    expected = doc({"type": "paragraph", "content": [text("a", mark), wrap(text("b", mark)), text("c", mark)]})
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markdown
