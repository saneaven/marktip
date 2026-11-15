"""Declared inline atoms and containers preserve their typed tag form."""

import time

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)
PARENT_PATH = "content[0]"


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x", *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def mark(type_, **attrs):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    return result


def node(type_, *children, attrs=None, marks=()):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    if marks:
        result["marks"] = list(marks)
    return result


def inline_schema(*, marks=()):
    return tm.Schema(nodes=[
        tm.NodeSpec("mention", kind="inline"),
        tm.NodeSpec("wrap", kind="inline", content="inline*"),
    ], marks=marks)


def roundtrip(ast, schema, markdown, html, level, expected=None, **options):
    source = tm.from_dict(ast, schema=schema, strict=level, **options)
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=schema, html=html, **options)
    assert parsed.to_dict() == (source.to_dict() if expected is None else expected)
    assert parsed.to_markdown(canonical=True) == markdown
    return parsed


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_, value, encoded", [
    (str, "", ""),
    (str, "café ' 한", "café ' 한"),
    (int, -(2**63), str(-(2**63))),
    (int, 2**63 - 1, str(2**63 - 1)),
    (int, 0, "0"),
    (bool, False, "false"),
    (bool, True, "true"),
])
@pytest.mark.parametrize("container", (False, True))
def test_inline_node_attr_types_roundtrip(html, level, type_, value, encoded, container):
    spec = tm.NodeSpec("note", kind="inline", tag="badge", content="inline*" if container else None,
                       attrs={"value": tm.Attr(type_)})
    schema = tm.Schema(nodes=[spec])
    child = node("note", *([text("x")] if container else []), attrs={"value": value})
    markdown = f'<badge value="{encoded}">x</badge>' if container else f'<badge value="{encoded}"/>'
    roundtrip(doc(p(child)), schema, markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("container", (False, True))
def test_inline_node_attrs_escape_controls_and_follow_declaration_order(html, level, container):
    schema = tm.Schema(nodes=[tm.NodeSpec("note", kind="inline", content="inline*" if container else None,
                                         attrs={"value": tm.Attr(str), "count": tm.Attr(int)})])
    value = '&"<>|`' + "".join(chr(number) for number in range(1, 32))
    encoded = "&amp;&quot;&lt;&gt;&#124;&#96;" + "".join(f"&#{number};" for number in range(1, 32))
    child = node("note", *([text("x")] if container else []), attrs={"count": -12, "value": value})
    ending = ">x</note>" if container else "/>"
    roundtrip(doc(p(child)), schema, f'<note value="{encoded}" count="-12"{ending}', html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("container", (False, True))
def test_inline_node_defaults_and_none_stay_unset(html, level, container):
    schema = tm.Schema(nodes=[tm.NodeSpec("note", kind="inline", content="inline*" if container else None,
                                         attrs={"tone": tm.Attr(str, choices=("red", "blue"), default="red"),
                                                "count": tm.Attr(int, default=0),
                                                "enabled": tm.Attr(bool, default=False),
                                                "optional": tm.Attr(str)})])
    child = node("note", *([text("x")] if container else []),
                 attrs={"tone": "red", "count": 0, "enabled": False, "optional": None})
    roundtrip(doc(p(child)), schema, "<note>x</note>" if container else "<note/>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_inline_node_uri_attrs_roundtrip_under_the_matching_policy(html, level):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("mention", kind="inline", attrs={"url": tm.Attr(str, uri="link")}),
        tm.NodeSpec("wrap", kind="inline", content="inline*", attrs={"src": tm.Attr(str, uri="image")}),
    ])
    ast = doc(p(node("mention", attrs={"url": "https://example.com/?a=1&b=2"}),
                node("wrap", text("x"), attrs={"src": "https://example.com/i.png"})))
    markdown = '<mention url="https://example.com/?a=1&amp;b=2"/><wrap src="https://example.com/i.png">x</wrap>'
    roundtrip(ast, schema, markdown, html, level, link_schemes=("https",), image_schemes=("https",))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("core, rendered", [
    (mark("bold"), "**<mention/>**"),
    (mark("italic"), "*<mention/>*"),
    (mark("strike"), "~~<mention/>~~"),
    (mark("link", href="https://example.com"), "[<mention/>](https://example.com)"),
])
@pytest.mark.parametrize("reverse", (False, True))
def test_inline_atoms_keep_core_and_declared_marks_in_both_input_orders(html, level, core, rendered, reverse):
    marks = [mark("underline"), core]
    if reverse:
        marks.reverse()
    schema = inline_schema(marks=[tm.MarkSpec("underline", tag="u")])
    roundtrip(doc(p(node("mention", marks=marks))), schema, f"<u>{rendered}</u>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("core, rendered", [
    (mark("bold"), "**x**"),
    (mark("italic"), "*x*"),
    (mark("strike"), "~~x~~"),
    (mark("code"), "`x`"),
    (mark("link", href="https://example.com"), "[x](https://example.com)"),
])
def test_inline_container_children_keep_each_core_and_declared_mark(html, level, core, rendered):
    schema = inline_schema(marks=[tm.MarkSpec("underline", tag="u")])
    roundtrip(doc(p(node("wrap", text("x", core, mark("underline"))))), schema,
              f"<wrap><u>{rendered}</u></wrap>", html, level)


@pytest.mark.parametrize("html", HTML)
def test_off_drops_only_the_code_mark_from_atoms_and_does_not_join_code_runs(html):
    schema = inline_schema(marks=[tm.MarkSpec("underline", tag="u")])
    code = mark("code")
    ast = doc(p(text("a", code), node("mention", marks=[code]), text("b", code)))
    expected = doc(p(text("a", code), node("mention"), text("b", code)))
    roundtrip(ast, schema, "`a`<mention/>`b`", html, "off", expected)
    ast = doc(p(node("mention", marks=[code, mark("bold"), mark("underline")])))
    expected = doc(p(node("mention", marks=[mark("bold"), mark("underline")])))
    roundtrip(ast, schema, "<u>**<mention/>**</u>", html, "off", expected)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("core, delimiter", (("bold", "**"), ("italic", "*"), ("strike", "~~"), ("code", "`")))
def test_inline_containers_are_barriers_to_mark_and_code_runs(html, level, core, delimiter):
    marks = [mark(core)]
    ast = doc(p(text("a", *marks), node("wrap", text("b", *marks)), text("c", *marks)))
    markdown = f"{delimiter}a{delimiter}<wrap>{delimiter}b{delimiter}</wrap>{delimiter}c{delimiter}"
    roundtrip(ast, inline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup, expected, written", [
    ("<u>a<wrap>b</u>c</wrap>d",
     doc(p(text("a", mark("underline")), node("wrap", text("b", mark("underline")), text("c")), text("d"))),
     "<u>a</u><wrap><u>b</u>c</wrap>d"),
    ("**a<wrap>b**c</wrap>d",
     doc(p(text("a", mark("bold")), node("wrap", text("b", mark("bold")), text("c")), text("d"))),
     "**a**<wrap>**b**c</wrap>d"),
    ("<wrap>a<u>b</wrap>c</u>",
     doc(p(node("wrap", text("a"), text("b", mark("underline"))), text("c", mark("underline")))),
     "<wrap>a<u>b</u></wrap><u>c</u>"),
])
def test_flat_mark_pairing_can_cross_inline_container_boundaries(html, markup, expected, written):
    schema = inline_schema(marks=[tm.MarkSpec("underline", tag="u")])
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == written
    assert tm.from_markdown(written, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_nested_named_group_less_members_roundtrip(html, level):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("ruby", kind="inline", content="text* rt?"),
        tm.NodeSpec("rt", kind="inline", content="inline*", group=""),
    ])
    ast = doc(p(text("before "), node("ruby", text("漢"), node("rt", text("かん", mark("bold")))),
                text(" after")))
    roundtrip(ast, schema, "before <ruby>漢<rt>**かん**</rt></ruby> after", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("content", (None, ""))
def test_empty_expression_and_none_declare_the_same_atom(html, level, content):
    schema = tm.Schema(nodes=[tm.NodeSpec("empty", kind="inline", content=content)])
    roundtrip(doc(p(text("a"), node("empty"), text("b"))), schema, "a<empty/>b", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("container", (False, True))
@pytest.mark.parametrize("context", ("paragraph", "heading", "quote", "bullet", "ordered", "task", "table"))
def test_declared_inline_shapes_roundtrip_in_core_contexts(html, level, container, context):
    child = node("wrap", text("x", mark("bold"))) if container else node("mention")
    carrier = "<wrap>**x**</wrap>" if container else "<mention/>"
    if context == "paragraph":
        ast, markdown = doc(p(child)), carrier
    elif context == "heading":
        ast, markdown = doc(node("heading", child, attrs={"level": 2})), "## " + carrier
    elif context == "quote":
        ast, markdown = doc(node("blockquote", p(child))), "> " + carrier
    elif context == "bullet":
        ast = doc(node("bulletList", node("listItem", p(child)), attrs={"tight": True}))
        markdown = "- " + carrier
    elif context == "ordered":
        ast = doc(node("orderedList", node("listItem", p(child)), attrs={"start": 3, "tight": True}))
        markdown = "3. " + carrier
    elif context == "task":
        ast = doc(node("taskList", node("taskItem", p(child), attrs={"checked": True}), attrs={"tight": True}))
        markdown = "- [x] " + carrier
    else:
        ast = doc(node("table", node("tableRow", node("tableHeader", p(child))), attrs={"colCount": 1}))
        markdown = "| " + carrier + " |\n| --- |"
    roundtrip(ast, inline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_hard_breaks_at_container_and_atom_edges_are_preserved(html, level):
    schema = inline_schema()
    br = node("hardBreak")
    ast = doc(p(text("a"), br, node("mention"), br, node("wrap", br, text("x"), br), br, text("b")))
    roundtrip(ast, schema, "a  \n<mention/>  \n<wrap>  \nx  \n</wrap>  \nb", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_table_cell_container_hard_breaks_use_the_core_br_form(html, level):
    ast = doc(node("table", node("tableRow", node("tableHeader", p(node("wrap", text("a"), node("hardBreak"),
                                                                         text("b"))))), attrs={"colCount": 1}))
    roundtrip(ast, inline_schema(), "| <wrap>a<br>b</wrap> |\n| --- |", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup", (
    "<wrap>",
    "</wrap>",
    "<wrap/>",
    "<wrap />",
    "<wrap/>x</wrap>",
    "</wrap/>",
    "<wrap><inner/></wrap>",
    "<wrap>x",
    "x</wrap>",
    "<wrap><inner>x</wrap></inner>",
    "<wrap><inner>x</inner>",
    "<wrap>a\n\nb</wrap>",
))
def test_inline_container_tags_must_close_in_the_same_inline_parent_and_nest(html, markup):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("wrap", kind="inline", content="inline*"),
        tm.NodeSpec("inner", kind="inline", content="inline*"),
    ])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema, html=html)
    assert excinfo.value.code == "invalid_tag"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup, expected_path", (
    ("<onlyText></onlyText>", "content[0].content[0]"),
    ("<onlyText><mention/></onlyText>", "content[0].content[0]"),
    ("before<onlyText><mention/></onlyText>", "content[0].content[1]"),
))
def test_read_content_expression_errors_locate_the_declared_container(html, markup, expected_path):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("mention", kind="inline"),
        tm.NodeSpec("onlyText", kind="inline", content="text+"),
    ])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema, html=html)
    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == expected_path


@pytest.mark.parametrize("html", HTML)
def test_two_thousand_nested_inline_containers_parse_without_a_deep_python_expected_tree(html):
    depth = 2000
    schema = inline_schema()
    markdown = "<wrap>" * depth + "x" + "</wrap>" * depth
    start = time.perf_counter()
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"2000 nested inline containers took {elapsed:.3f}s"
    assert parsed.to_markdown(canonical=True) == markdown
    child = parsed.to_dict()["content"][0]
    for _ in range(depth):
        assert child["type"] in ("paragraph", "wrap")
        child = child["content"][0]
    assert child == node("wrap", text("x"))


@pytest.mark.parametrize("html", HTML)
def test_twenty_thousand_nested_inline_containers_refuse_depth_without_overflowing_the_worker_stack(html):
    schema = inline_schema()
    markdown = "<wrap>" * 20000 + "x" + "</wrap>" * 20000
    start = time.perf_counter()
    with pytest.raises(tm.ParseError) as excinfo:
        tm.from_markdown(markdown, schema=schema, html=html)
    elapsed = time.perf_counter() - start
    assert excinfo.value.code == "markdown_max_depth"
    assert excinfo.value.path == ""
    assert elapsed < 1.0, f"over-depth inline containers took {elapsed:.3f}s"


@pytest.mark.parametrize("html", HTML)
def test_twenty_thousand_sibling_inline_atoms_stay_separate_in_under_one_second(html):
    count = 20000
    schema = inline_schema()
    markdown = "<mention/>" * count
    start = time.perf_counter()
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"20000 sibling inline atoms took {elapsed:.3f}s"
    children = parsed.to_dict()["content"][0]["content"]
    assert len(children) == count
    assert all(child == node("mention") for child in children)
    assert parsed.to_markdown(canonical=True) == markdown


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("container", (False, True))
def test_group_less_inline_nodes_require_a_parent_that_names_them(html, container):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("isolated", kind="inline", content="inline*" if container else None, group=""),
        tm.NodeSpec("host", kind="inline", content="isolated"),
    ])
    child = node("isolated", *([text("x")] if container else []))
    carrier = "<isolated>x</isolated>" if container else "<isolated/>"
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(carrier, schema=schema, html=html)
    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == "content[0].content[0]"
    parsed = tm.from_markdown(f"<host>{carrier}</host>", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(node("host", child)))
    assert parsed.to_markdown(canonical=True) == f"<host>{carrier}</host>"
