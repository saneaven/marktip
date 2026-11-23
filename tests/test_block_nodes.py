"""Declared block shapes write and read their typed carriers in ordinary documents."""

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)
SHAPES = ("atom", "container", "textblock")


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


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def block_schema():
    return tm.Schema(nodes=[
        tm.NodeSpec("embed", kind="block"),
        tm.NodeSpec("callout", kind="block", content="block*"),
        tm.NodeSpec("summary", kind="block", content="inline*"),
    ])


def shape_node(shape, *, type_=None, attrs=None):
    if shape == "atom":
        return node(type_ or "embed", attrs=attrs)
    if shape == "container":
        return node(type_ or "callout", p(text("x")), attrs=attrs)
    return node(type_ or "summary", text("x"), attrs=attrs)


def carrier(shape, *, tag=None, attrs=""):
    tag = tag or {"atom": "embed", "container": "callout", "textblock": "summary"}[shape]
    if shape == "atom":
        return f"<{tag}{attrs}/>"
    if shape == "container":
        return f"<{tag}{attrs}>\n\nx\n\n</{tag}>"
    return f"<{tag}{attrs}>x</{tag}>"


def roundtrip(ast, schema, markdown, html, level, expected=None, **options):
    source = tm.from_dict(ast, schema=schema, strict=level, **options)
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=schema, html=html, **options)
    assert parsed.to_dict() == (source.to_dict() if expected is None else expected)
    assert parsed.to_markdown(canonical=True) == markdown
    return parsed


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
def test_block_shapes_roundtrip_alone(html, level, shape):
    roundtrip(doc(shape_node(shape)), block_schema(), carrier(shape), html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("type_, value, encoded", [
    (str, "", ""),
    (str, "café ' 한", "café ' 한"),
    (int, -(2**63), str(-(2**63))),
    (int, 2**63 - 1, str(2**63 - 1)),
    (int, 0, "0"),
    (bool, False, "false"),
    (bool, True, "true"),
])
def test_block_shape_attr_types_and_explicit_tags_roundtrip(html, level, shape, type_, value, encoded):
    content = {"atom": None, "container": "block*", "textblock": "inline*"}[shape]
    schema = tm.Schema(nodes=[tm.NodeSpec("widget", kind="block", tag="sample", content=content,
                                         attrs={"value": tm.Attr(type_)})])
    ast = doc(shape_node(shape, type_="widget", attrs={"value": value}))
    roundtrip(ast, schema, carrier(shape, tag="sample", attrs=f' value="{encoded}"'), html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
def test_block_shape_attr_escaping_and_declaration_order_roundtrip(html, level, shape):
    content = {"atom": None, "container": "block*", "textblock": "inline*"}[shape]
    schema = tm.Schema(nodes=[tm.NodeSpec("widget", kind="block", tag="sample", content=content,
                                         attrs={"value": tm.Attr(str), "count": tm.Attr(int)})])
    value = '&"<>|`' + "".join(chr(number) for number in range(1, 32))
    encoded = "&amp;&quot;&lt;&gt;&#124;&#96;" + "".join(f"&#{number};" for number in range(1, 32))
    ast = doc(shape_node(shape, type_="widget", attrs={"count": -12, "value": value}))
    roundtrip(ast, schema, carrier(shape, tag="sample", attrs=f' value="{encoded}" count="-12"'), html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
def test_block_shape_defaults_and_none_are_not_materialized(html, level, shape):
    content = {"atom": None, "container": "block*", "textblock": "inline*"}[shape]
    schema = tm.Schema(nodes=[tm.NodeSpec("widget", kind="block", tag="sample", content=content, attrs={
        "tone": tm.Attr(str, choices=("info", "warning"), default="info"),
        "count": tm.Attr(int, default=0), "enabled": tm.Attr(bool, default=False), "optional": tm.Attr(str),
    })])
    ast = doc(shape_node(shape, type_="widget",
                         attrs={"tone": "info", "count": 0, "enabled": False, "optional": None}))
    roundtrip(ast, schema, carrier(shape, tag="sample"), html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_block_node_uri_attrs_keep_the_corresponding_policy(html, level):
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", kind="block", attrs={"url": tm.Attr(str, uri="link"),
                                                                         "src": tm.Attr(str, uri="image")})])
    ast = doc(node("embed", attrs={"url": "https://example.com/?a=1&b=2", "src": "https://example.com/i.png"}))
    markdown = '<embed url="https://example.com/?a=1&amp;b=2" src="https://example.com/i.png"/>'
    roundtrip(ast, schema, markdown, html, level, link_schemes=("https",), image_schemes=("https",))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_block_containers_nest_around_atoms_containers_and_textblocks(html, level):
    ast = doc(node("callout", p(text("before")), node("embed"), node("callout", p(text("inner"))),
                   node("summary", text("title", mark("bold"))), p(text("after"))))
    markdown = ("<callout>\n\nbefore\n\n<embed/>\n\n<callout>\n\ninner\n\n</callout>\n\n"
                "<summary>**title**</summary>\n\nafter\n\n</callout>")
    roundtrip(ast, block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("neighbor, written", [
    (p(text("neighbor")), "neighbor"),
    (node("heading", text("neighbor"), attrs={"level": 2}), "## neighbor"),
    (node("horizontalRule"), "---"),
    (node("codeBlock", text("neighbor")), "```\nneighbor\n```"),
    (node("blockquote", p(text("neighbor"))), "> neighbor"),
    (node("bulletList", node("listItem", p(text("neighbor"))), attrs={"tight": True}), "- neighbor"),
    (node("table", node("tableRow", node("tableHeader", p(text("neighbor")))), attrs={"colCount": 1}),
     "| neighbor |\n| --- |"),
])
def test_block_shapes_separate_core_siblings_on_both_sides(html, level, shape, neighbor, written):
    ast = doc(neighbor, shape_node(shape), neighbor)
    roundtrip(ast, block_schema(), f"{written}\n\n{carrier(shape)}\n\n{written}", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
def test_block_shapes_roundtrip_inside_a_blockquote(html, level, shape):
    ast = doc(node("blockquote", shape_node(shape)))
    markdown = "\n".join("> " + line if line else ">" for line in carrier(shape).split("\n"))
    roundtrip(ast, block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("family", ("bullet", "ordered", "task"))
@pytest.mark.parametrize("tight", (True, False))
def test_block_shapes_can_be_the_first_block_in_tight_and_loose_list_items(html, level, shape, family, tight):
    if family == "task":
        first_marker, second_marker, item_type = "- [x] ", "- [ ] ", "taskItem"
        first_attrs, second_attrs = {"checked": True}, {"checked": False}
        list_type, list_attrs = "taskList", {"tight": tight}
    elif family == "ordered":
        first_marker, second_marker, item_type = "3. ", "4. ", "listItem"
        first_attrs, second_attrs = None, None
        list_type, list_attrs = "orderedList", {"start": 3, "tight": tight}
    else:
        first_marker, second_marker, item_type = "- ", "- ", "listItem"
        first_attrs, second_attrs = None, None
        list_type, list_attrs = "bulletList", {"tight": tight}
    ast = doc(node(list_type,
                   node(item_type, shape_node(shape), attrs=first_attrs),
                   node(item_type, p(text("after")), attrs=second_attrs), attrs=list_attrs))
    inside = carrier(shape).replace("\n\n", "\n") if shape == "container" else carrier(shape)
    lines = inside.split("\n")
    continuation = 2 if family == "task" else len(first_marker)
    if family == "task" and shape != "textblock":
        first = first_marker.rstrip() + "\n" + " " * continuation + lines[0]
    else:
        first = first_marker + lines[0]
    first += "".join("\n" + " " * continuation + line for line in lines[1:])
    markdown = first + ("\n" if tight else "\n\n") + second_marker + "after"
    roundtrip(ast, block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", ("atom", "container"))
def test_tag_lines_do_not_make_a_tight_list_item_loose(html, level, shape):
    ast = doc(node("bulletList", node("listItem", p(text("before")), shape_node(shape)),
                   node("listItem", p(text("after"))), attrs={"tight": True}))
    body = carrier(shape).replace("\n\n", "\n").replace("\n", "\n  ")
    roundtrip(ast, block_schema(), f"- before\n  {body}\n- after", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_textblock_forms_require_blank_lines_between_blocks_in_a_list_item(html, level):
    ast = doc(node("bulletList", node("listItem", p(text("before")), node("summary", text("title")),
                                     p(text("after"))),
                   node("listItem", p(text("second"))), attrs={"tight": False}))
    markdown = "- before\n\n  <summary>title</summary>\n\n  after\n\n- second"
    roundtrip(ast, block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("shape", ("atom", "textblock"))
def test_block_atoms_and_textblocks_have_one_line_forms_in_table_cells(html, level, shape):
    child = shape_node(shape)
    ast = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
    roundtrip(ast, block_schema(), f"| {carrier(shape)} |\n| --- |", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_textblock_hard_breaks_use_br_inside_a_table_cell(html, level):
    child = node("summary", text("a"), node("hardBreak"), text("b"))
    ast = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
    roundtrip(ast, block_schema(), "| <summary>a<br>b</summary> |\n| --- |", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_textblock_body_keeps_inline_marks_and_hard_breaks(html, level):
    schema = tm.Schema(nodes=[tm.NodeSpec("summary", kind="block", content="inline*")],
                       marks=[tm.MarkSpec("underline", tag="u")])
    child = node("summary", text("title", mark("bold"), mark("underline")), node("hardBreak"), text("body"))
    roundtrip(doc(child), schema, "<summary><u>**title**</u>\\\nbody</summary>", html, level)


def test_declared_textblock_keeps_required_whitespace_text():
    schema = tm.Schema(nodes=[tm.NodeSpec("caption", "block", tag="custom-caption", content="text+")])
    markdown = "<custom-caption> </custom-caption>"
    ast = doc(node("caption", text(" ")))

    parsed = tm.from_markdown(markdown, schema=schema)
    assert parsed.to_dict() == ast
    assert parsed.to_markdown(canonical=True) == markdown

    created = tm.from_dict(ast, schema=schema, strict="content")
    assert created == parsed
    assert created.to_markdown(canonical=True) == markdown


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_empty_block_atom_container_and_textblock_keep_their_distinct_forms(html, level):
    ast = doc(node("embed"), node("callout"), node("summary"))
    markdown = "<embed/>\n\n<callout>\n\n</callout>\n\n<summary></summary>"
    roundtrip(ast, block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_empty_paragraphs_in_optional_block_content_are_dropped(html, level):
    ast = doc(node("callout", p(text("before")), p(), p(text("after"))))
    expected = doc(node("callout", p(text("before")), p(text("after"))))
    roundtrip(ast, block_schema(), "<callout>\n\nbefore\n\nafter\n\n</callout>", html, level, expected)
    roundtrip(doc(node("callout", p())), block_schema(), "<callout>\n\n</callout>", html, level,
              doc(node("callout")))


@pytest.mark.parametrize("content", ("paragraph*", "block*", "legacyEmbed|paragraph"))
def test_declared_container_writes_its_sole_empty_paragraph(content):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("callout", "block", content=content),
        tm.NodeSpec("legacyEmbed", "block", group=""),
    ], core_attrs={"paragraph": {}})
    ast = doc(node("callout", node("paragraph")))
    roundtrip(ast, schema, "<callout>\n\n<p></p>\n\n</callout>", html=True, level="content", expected=ast)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_required_block_content_restores_one_empty_paragraph(html, level):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", kind="block", content="block+")])
    roundtrip(doc(node("callout", p())), schema, "<callout>\n\n</callout>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("core_attrs, canonical", [
    ({}, "<callout>\n\n</callout>"),
    ({"paragraph": {}}, "<callout>\n\n<p></p>\n\n</callout>"),
])
def test_reading_an_empty_required_container_fills_one_empty_paragraph(html, core_attrs, canonical):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", kind="block", content="paragraph+")], core_attrs=core_attrs)
    parsed = tm.from_markdown("<callout>\n\n</callout>", schema=schema, html=html)
    assert parsed.to_dict() == doc(node("callout", node("paragraph")))
    assert parsed.to_markdown(canonical=True) == canonical
    assert tm.from_markdown(canonical, schema=schema, html=html) == parsed


def details_schema():
    return tm.Schema(nodes=[
        tm.NodeSpec("details", kind="block", content="detailsSummary detailsContent",
                    attrs={"open": tm.Attr(bool, default=False)}),
        tm.NodeSpec("detailsSummary", kind="block", tag="summary", content="inline*", group=""),
        tm.NodeSpec("detailsContent", kind="block", content="block+", group="", implicit=True),
    ])


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("opened", (None, False, True))
def test_details_implicit_wrapper_uses_the_human_tag_shape(html, level, opened):
    ast = doc(node("details", node("detailsSummary", text("Title")), node("detailsContent", p(text("Body"))),
                   attrs={} if opened is None else {"open": opened}))
    opening = '<details open="true">' if opened else "<details>"
    markdown = opening + "\n\n<summary>Title</summary>\n\nBody\n\n</details>"
    roundtrip(ast, details_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_implicit_wrapper_can_contain_a_nested_details_block(html, level):
    nested = node("details", node("detailsSummary", text("Inner")), node("detailsContent", p(text("Body"))))
    ast = doc(node("details", node("detailsSummary", text("Outer")), node("detailsContent", p(text("Intro")), nested)))
    markdown = ("<details>\n\n<summary>Outer</summary>\n\nIntro\n\n<details>\n\n<summary>Inner</summary>\n\n"
                "Body\n\n</details>\n\n</details>")
    roundtrip(ast, details_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("core_attrs, markdown", [
    ({}, "<details>\n\n<summary>Title</summary>\n\n</details>"),
    ({"paragraph": {}}, "<details>\n\n<summary>Title</summary>\n\n<p></p>\n\n</details>"),
])
def test_empty_required_implicit_content_restores_one_empty_paragraph(html, level, core_attrs, markdown):
    ast = doc(node("details", node("detailsSummary", text("Title")), node("detailsContent", p())))
    roundtrip(ast, details_schema().extend(core_attrs=core_attrs), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_implicit_details_separates_core_siblings(html, level):
    child = node("details", node("detailsSummary", text("Title")), node("detailsContent", p(text("Body"))))
    ast = doc(p(text("before")), child, p(text("after")))
    markdown = "before\n\n<details>\n\n<summary>Title</summary>\n\nBody\n\n</details>\n\nafter"
    roundtrip(ast, details_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("context", ("quote", "bullet", "ordered", "task"))
def test_implicit_details_roundtrip_in_quotes_and_loose_list_items(html, level, context):
    child = node("details", node("detailsSummary", text("Title")), node("detailsContent", p(text("Body"))))
    if context == "quote":
        ast = doc(node("blockquote", child))
        markdown = "> <details>\n>\n> <summary>Title</summary>\n>\n> Body\n>\n> </details>"
    else:
        if context == "task":
            family, item = "taskList", "taskItem"
            first_marker, second_marker = "- [x] ", "- [ ] "
            first_attrs, second_attrs = {"checked": True}, {"checked": False}
            attrs = {"tight": False}
        elif context == "ordered":
            family, item = "orderedList", "listItem"
            first_marker, second_marker = "2. ", "3. "
            first_attrs, second_attrs = None, None
            attrs = {"start": 2, "tight": False}
        else:
            family, item = "bulletList", "listItem"
            first_marker = second_marker = "- "
            first_attrs, second_attrs = None, None
            attrs = {"tight": False}
        ast = doc(node(family, node(item, child, attrs=first_attrs),
                       node(item, p(text("after")), attrs=second_attrs), attrs=attrs))
        lines = ("", "<summary>Title</summary>", "", "Body", "</details>")
        continuation = 2 if context == "task" else len(first_marker)
        opening = first_marker.rstrip() + "\n  <details>" if context == "task" else first_marker + "<details>"
        markdown = opening + "".join(
            "\n" + (" " * continuation + line if line else "") for line in lines
        ) + "\n\n" + second_marker + "after"
    roundtrip(ast, details_schema(), markdown, html, level)
