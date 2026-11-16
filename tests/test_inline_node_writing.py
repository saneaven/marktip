"""Writer rules for inline containers and their own marks."""

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
@pytest.mark.parametrize("level", ("off", "content", "exact"))
@pytest.mark.parametrize("mark, markdown", (
    ({"type": "bold"}, "**a<wrap>b</wrap>c**"),
    ({"type": "italic"}, "*a<wrap>b</wrap>c*"),
    ({"type": "strike"}, "~~a<wrap>b</wrap>c~~"),
    ({"type": "link", "attrs": {"href": "https://example.com"}},
     "[a<wrap>b</wrap>c](https://example.com)"),
    ({"type": "underline"}, "<u>a<wrap>b</wrap>c</u>"),
))
def test_container_own_marks_share_a_run_with_neighbours(html, level, mark, markdown):
    schema = tm.Schema(nodes=[tm.NodeSpec("wrap", kind="inline", content="inline*")],
                       marks=[tm.MarkSpec("underline", tag="u")])
    children = [text("a", mark), wrap(text("b"), marks=[mark]), text("c", mark)]
    source = tm.from_dict(doc({"type": "paragraph", "content": children}), schema=schema, strict=level)
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == markdown
