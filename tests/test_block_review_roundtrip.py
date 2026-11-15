"""Block carriers preserve their boundaries in ordinary list and textblock content."""

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value):
    return {"type": "text", "text": value}


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def schema():
    return tm.Schema(nodes=[
        tm.NodeSpec("callout", kind="block", content="block*"),
        tm.NodeSpec("embed", kind="block"),
        tm.NodeSpec("lead", kind="block", content="inline*"),
    ])


def table():
    return node("table",
                node("tableRow", node("tableHeader", p(text("h")))),
                node("tableRow", node("tableCell", p(text("v")))), attrs={"colCount": 1})


def loose_list(*blocks):
    return doc(node("bulletList", node("listItem", *blocks),
                    node("listItem", p(text("after"))), attrs={"tight": False}))


def roundtrip(ast, declarations, markdown, html, level):
    source = tm.from_dict(ast, schema=declarations, strict=level)
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=declarations, html=html)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == markdown


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_table_inside_a_list_container_ends_before_the_closing_tag(html, level):
    ast = loose_list(node("callout", table()))
    markdown = "- <callout>\n  | h |\n  | --- |\n  | v |\n\n  </callout>\n\n- after"
    roundtrip(ast, schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_table_in_a_list_item_ends_before_the_next_atom(html, level):
    ast = loose_list(table(), node("embed"))
    markdown = "- | h |\n  | --- |\n  | v |\n\n  <embed/>\n\n- after"
    roundtrip(ast, schema(), markdown, html, level)


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("wrapped, following_atom", [(False, True), (True, True), (True, False)])
def test_raw_html_in_a_list_ends_before_the_next_carrier(level, wrapped, following_atom):
    children = [node("htmlBlock", attrs={"html": "<div>raw</div>\n"})]
    if following_atom:
        children.append(node("embed"))
    ast = loose_list(node("callout", *children)) if wrapped else loose_list(*children)
    body = "<div>raw</div>\n\n\n  "
    if following_atom:
        body += "<embed/>"
    if wrapped:
        body = "<callout>\n  " + body + ("\n  " if following_atom else "") + "</callout>"
    roundtrip(ast, schema(), "- " + body + "\n\n- after", True, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("marker, escaped", [
    ("1.", "1\\."),
    ("-", "\\-"),
    ("+", "\\+"),
    (">", "\\>"),
])
def test_textblock_continuation_line_markers_stay_text(html, level, marker, escaped):
    ast = doc(node("lead", text("first"), node("hardBreak"), text(f"{marker} next")))
    roundtrip(ast, schema(), f"<lead>first  \n{escaped} next</lead>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_filled_empty_paragraph_inside_a_list_container_keeps_the_list_tight(html, level):
    declarations = tm.Schema(nodes=[tm.NodeSpec("callout", kind="block", content="paragraph+")])
    ast = doc(node("bulletList", node("listItem", node("callout", p())),
                   node("listItem", p(text("after"))), attrs={"tight": True}))
    roundtrip(ast, declarations, "- <callout>\n  </callout>\n- after", html, level)


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("declared", (False, True))
@pytest.mark.parametrize("children, markdown", [
    ((p(),), "- "),
    ((p(), p(text("x"))), "- \n\n  x"),
])
def test_direct_empty_list_item_paragraph_bytes_are_unchanged(level, declared, children, markdown):
    ast = doc(node("bulletList", node("listItem", *children), attrs={"tight": False}))
    source = tm.from_dict(ast, schema=schema() if declared else None, strict=level)
    assert source.to_markdown(canonical=True) == markdown
