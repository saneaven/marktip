"""Core container tag forms preserve their families and ordinary parent contexts."""

import pytest

import marktip as tm


HTML = (True, False)
LIST_TYPES = ("bulletList", "orderedList", "taskList", "listItem", "taskItem")
TABLE_TYPES = ("table", "tableRow", "tableHeader", "tableCell")


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


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def table(*rows, attrs=None):
    return node("table", *rows, attrs={"colCount": 1, **(attrs or {})})


def core_schema():
    return tm.Schema(
        core_attrs={type_: {"label": tm.Attr(str)} for type_ in ("blockquote", *LIST_TYPES, *TABLE_TYPES)},
        marks=[tm.MarkSpec("underline", tag="u")],
        nodes=[tm.NodeSpec("mention", "inline", attrs={"id": tm.Attr(str, required=True)}),
               tm.NodeSpec("callout", "block", content="block*")],
    )


def roundtrip(ast, schema, html=True):
    source = tm.from_dict(ast, schema=schema, strict="exact")
    written = source.to_markdown(canonical=True)
    parsed = tm.from_markdown(written, schema=schema, html=html)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == written
    return written


def in_context(child, context):
    if context == "root":
        return doc(child)
    if context == "quote":
        return doc(node("blockquote", child))
    if context == "list":
        return doc(node("bulletList", node("listItem", p(text("before")), child, p(text("after"))),
                        node("listItem", p(text("next"))), attrs={"tight": False}))
    return doc(table(node("tableRow", node("tableHeader", child))))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("context", ("root", "quote", "list", "table"))
@pytest.mark.parametrize("family", ("quote", "list", "table"))
def test_core_container_tag_forms_roundtrip_in_each_allowed_parent_context(html, context, family):
    content = p(text("x", mark("bold"), mark("underline")), node("mention", attrs={"id": "u1"}))
    if family == "quote":
        child = node("blockquote", content, attrs={"label": "note"})
        opening = '<blockquote label="note">'
    elif family == "list":
        child = node("bulletList", node("listItem", content), node("listItem", p(text("second"))),
                     attrs={"tight": True, "label": "notes"})
        opening = '<ul tight="true" label="notes">'
    else:
        child = table(node("tableRow", node("tableHeader", content)),
                      node("tableRow", node("tableCell", p(text("value")))), attrs={"label": "grid"})
        opening = '<table colCount="1" label="grid">'
    written = roundtrip(in_context(child, context), core_schema(), html)
    assert opening in written
    assert '<u>**x**</u><mention id="u1"/>' in written


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("list_type, item_type, tag, attrs", [
    ("bulletList", "listItem", "ul", {"tight": True}),
    ("orderedList", "listItem", "ol", {"start": 3, "tight": True}),
    ("taskList", "taskItem", "ul", {"tight": True}),
])
def test_an_item_overlay_promotes_its_list_and_all_sibling_items(html, list_type, item_type, tag, attrs):
    first_attrs = {"label": "first"}
    second_attrs = {}
    if item_type == "taskItem":
        first_attrs["checked"] = True
        second_attrs["checked"] = False
    child = node(list_type, node(item_type, p(text("one")), attrs=first_attrs),
                 node(item_type, p(text("two")), attrs=second_attrs), attrs=attrs)
    written = roundtrip(doc(child), core_schema(), html)
    assert f"<{tag} " in written
    assert written.count("<li") == 2
    assert written.count("</li>") == 2
    assert 'label="first"' in written
    if item_type == "taskItem":
        assert '<li checked="true" label="first">' in written
        assert '<li checked="false">' in written


@pytest.mark.parametrize("html", HTML)
def test_list_tags_write_carried_attrs_then_overlay_attrs_in_declaration_order(html):
    schema = tm.Schema(core_attrs={"orderedList": {"style": tm.Attr(str), "type": tm.Attr(str)},
                                   "listItem": {"data-id": tm.Attr(str), "rank": tm.Attr(int)}})
    ast = doc(node("orderedList", node("listItem", p(text("one")), attrs={"rank": 2, "data-id": "first"}),
                   attrs={"type": "a", "style": "compact", "tight": True, "start": 3}))
    written = roundtrip(ast, schema, html)
    assert '<ol start="3" tight="true" style="compact" type="a">' in written
    assert '<li data-id="first" rank="2">' in written


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("checked, value", [("checked", True), ('checked="false"', False)])
def test_li_checked_presence_selects_task_item_even_when_the_value_is_false(html, checked, value):
    schema = tm.Schema(core_attrs={"listItem": {}})
    markup = f'<ul tight="true">\n\n<li {checked}>\n\nwork\n\n</li>\n\n</ul>'
    expected = doc(node("taskList", node("taskItem", p(text("work")), attrs={"checked": value}),
                        attrs={"tight": True}))
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == expected
    written = parsed.to_markdown(canonical=True)
    assert written == ("- [x] work" if value else "- [ ] work")
    assert tm.from_markdown(written, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
def test_unchecked_li_attrs_are_decoded_before_task_list_normalization(html):
    schema = tm.Schema(core_attrs={"taskList": {"label": tm.Attr(str)},
                                   "taskItem": {"rank": tm.Attr(int)}})
    markdown = ('<ul tight="true" label="work">\n\n<li checked="false" rank="1">\n\none\n\n</li>\n\n'
                '<li rank="2">\n\ntwo\n\n</li>\n\n</ul>')
    expected = doc(node("taskList",
                        node("taskItem", p(text("one")), attrs={"checked": False, "rank": 1}),
                        node("taskItem", p(text("two")), attrs={"checked": False, "rank": 2}),
                        attrs={"tight": True, "label": "work"}))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=schema, html=html)
    assert (excinfo.value.code, excinfo.value.field, excinfo.value.path) == ("unknown_attr", "rank", "")
    markdown = markdown.replace('<li rank="2">', '<li checked="false" rank="2">')
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    assert parsed.to_dict() == expected
    roundtrip(expected, schema, html)


def test_a_tag_form_task_item_always_writes_its_checked_attr():
    schema = tm.Schema(core_attrs={"taskList": {"label": tm.Attr(str)}})
    ast = doc(node("taskList", node("taskItem", p(text("work"))), attrs={"tight": True, "label": "tasks"}))
    written = tm.from_dict(ast, schema=schema, strict="exact").to_markdown(canonical=True)
    assert '<li checked="false">' in written
    parsed = tm.from_markdown(written, schema=schema)
    assert parsed.to_dict()["content"][0]["content"][0]["attrs"] == {"checked": False}
    assert parsed.to_markdown(canonical=True) == written


@pytest.mark.parametrize("html", HTML)
def test_one_checked_li_normalizes_the_other_ul_items_to_unchecked_task_items(html):
    schema = tm.Schema(core_attrs={"taskItem": {"label": tm.Attr(str)}})
    markup = ('<ul tight="true">\n\n<li checked="true" label="first">\n\none\n\n</li>\n\n'
              '<li>\n\ntwo\n\n</li>\n\n</ul>')
    expected = doc(node("taskList", node("taskItem", p(text("one")), attrs={"checked": True, "label": "first"}),
                        node("taskItem", p(text("two")), attrs={"checked": False}), attrs={"tight": True}))
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == expected
    written = parsed.to_markdown(canonical=True)
    assert '<li checked="false">' in written
    assert tm.from_markdown(written, schema=schema, html=html).to_dict() == expected
    assert tm.from_markdown(written, schema=schema, html=html).to_markdown(canonical=True) == written


@pytest.mark.parametrize("type_", LIST_TYPES)
def test_any_list_type_activates_the_ul_ol_and_li_tag_family(type_):
    schema = tm.Schema(core_attrs={type_: {}})
    markup = '<ol start="3" tight="true">\n\n<li>\n\none\n\n</li>\n\n</ol>'
    expected = doc(node("orderedList", node("listItem", p(text("one"))), attrs={"start": 3, "tight": True}))
    parsed = tm.from_markdown(markup, schema=schema)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == "3. one"
    ul = tm.from_markdown('<ul tight="true">\n\n<li checked="false">\n\ntwo\n\n</li>\n\n</ul>', schema=schema)
    assert ul.to_dict() == doc(node("taskList", node("taskItem", p(text("two")), attrs={"checked": False}),
                                   attrs={"tight": True}))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("rows", [
    (node("tableRow", node("tableCell", p(text("a"))), node("tableCell", p(text("b")))),),
    (node("tableRow", node("tableHeader", p(text("a"))), node("tableCell", p(text("b")))),),
    (node("tableRow", node("tableHeader", p(text("a"))), node("tableHeader", p(text("b")))),
     node("tableRow", node("tableHeader", p(text("c"))), node("tableCell", p(text("d"))))),
])
def test_noncanonical_header_rows_promote_the_table_without_changing_cell_types(html, rows):
    ast = doc(node("table", *rows, attrs={"colCount": 2}))
    written = roundtrip(ast, tm.Schema(core_attrs={"tableCell": {}}), html)
    assert written.startswith('<table colCount="2">')
    assert "<td>" in written


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("children", [(p(text("first")), p(text("second"))),
                                     (node("callout", p(text("inside"))),)])
def test_multiple_cell_blocks_and_declared_block_containers_promote_the_table(html, children):
    ast = doc(table(node("tableRow", node("tableHeader", *children))))
    written = roundtrip(ast, core_schema(), html)
    assert written.startswith('<table colCount="1">')
    assert "<th>" in written


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("children, tag_form", [
    ((), False),
    ((p(text("value")),), False),
    ((p(text("first")), p(text("second"))), True),
    ((node("blockquote", p(text("quoted"))),), True),
])
def test_cell_shape_uses_markdown_for_zero_children_or_one_paragraph(html, children, tag_form):
    ast = doc(table(node("tableRow", node("tableHeader", p(text("A")))),
                    node("tableRow", node("tableCell", *children))))
    written = roundtrip(ast, core_schema(), html)
    if tag_form:
        assert written.startswith('<table colCount="1">')
    else:
        assert written.startswith("| A |\n| --- |")


@pytest.mark.parametrize("html", HTML)
def test_table_spans_and_int_list_column_widths_roundtrip_in_tag_forms(html):
    schema = tm.Schema(core_attrs={
        "tableHeader": {"colspan": tm.Attr(int), "colwidth": tm.Attr(tm.IntList)},
        "tableCell": {"rowspan": tm.Attr(int)},
    })
    ast = doc(node("table",
                   node("tableRow", node("tableHeader", p(text("heading")),
                                          attrs={"colspan": 2, "colwidth": [100, 200]})),
                   node("tableRow", node("tableCell", p(text("left")), attrs={"rowspan": 2}),
                        node("tableCell", p(text("right")))),
                   node("tableRow", node("tableCell", p(text("next")))), attrs={"colCount": 2}))
    written = roundtrip(ast, schema, html)
    assert '<th colspan="2" colwidth="100,200">' in written
    assert '<td rowspan="2">' in written


@pytest.mark.parametrize("html", HTML)
def test_undeclared_unit_cell_spans_stay_stored_but_are_not_written_in_tag_forms(html):
    schema = tm.Schema(core_attrs={"table": {"label": tm.Attr(str)}})
    spans = {"colspan": 1, "rowspan": 1}
    ast = doc(table(node("tableRow", node("tableHeader", p(text("heading")), attrs=spans)),
                    node("tableRow", node("tableCell", p(text("value")), attrs=spans)), attrs={"label": "grid"}))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    assert source.to_dict() == ast
    written = source.to_markdown(canonical=True)
    assert "<th>" in written
    assert "<td>" in written
    assert "colspan" not in written
    assert "rowspan" not in written
    expected = doc(table(node("tableRow", node("tableHeader", p(text("heading")))),
                         node("tableRow", node("tableCell", p(text("value")))), attrs={"label": "grid"}))
    parsed = tm.from_markdown(written, schema=schema, html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == written


@pytest.mark.parametrize("html", HTML)
def test_table_row_and_cell_tags_write_carried_attrs_then_declared_attrs_in_order(html):
    schema = tm.Schema(core_attrs={
        "table": {"data-title": tm.Attr(str), "enabled": tm.Attr(bool)},
        "tableRow": {"data-row": tm.Attr(str), "order": tm.Attr(int)},
        "tableHeader": {"colwidth": tm.Attr(tm.IntList), "rowspan": tm.Attr(int), "colspan": tm.Attr(int)},
    })
    cell = node("tableHeader", p(text("x")), attrs={"colspan": 1, "align": "center", "rowspan": 1, "colwidth": [100]})
    row = node("tableRow", cell, attrs={"order": 1, "data-row": "top"})
    ast = doc(table(row, attrs={"enabled": True, "data-title": "grid"}))
    written = roundtrip(ast, schema, html)
    assert '<table colCount="1" data-title="grid" enabled="true">' in written
    assert '<tr data-row="top" order="1">' in written
    assert '<th align="center" colwidth="100" rowspan="1" colspan="1">' in written


@pytest.mark.parametrize("type_", TABLE_TYPES)
def test_any_table_type_activates_the_whole_table_tag_family(type_):
    schema = tm.Schema(core_attrs={type_: {}})
    markup = ('<table colCount="1">\n\n<tr>\n\n<th>\n\nheading\n\n</th>\n\n</tr>\n\n'
              '<tr>\n\n<td>\n\nvalue\n\n</td>\n\n</tr>\n\n</table>')
    expected = doc(table(node("tableRow", node("tableHeader", p(text("heading")))),
                         node("tableRow", node("tableCell", p(text("value"))))))
    parsed = tm.from_markdown(markup, schema=schema)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == "| heading |\n| --- |\n| value |"


def test_an_empty_ul_tag_reads_as_a_bullet_list():
    schema = tm.Schema(core_attrs={"taskList": {}})
    parsed = tm.from_markdown('<ul tight="true">\n\n</ul>', schema=schema)
    assert parsed.to_dict() == doc(node("bulletList", attrs={"tight": True}))
    assert parsed.to_markdown(canonical=True) == tm.from_dict(doc(node("bulletList", attrs={"tight": True}))).to_markdown(canonical=True)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("type_, attrs", [("bulletList", {"tight": True}),
                                        ("orderedList", {"start": 3, "tight": True}),
                                        ("taskList", {"tight": True}), ("table", {})])
def test_empty_lists_and_tables_with_unset_overlays_keep_no_schema_behavior(html, type_, attrs):
    schema = tm.Schema(core_attrs={type_: {"label": tm.Attr(str)}})
    ast = doc(node(type_, attrs=attrs))
    baseline = tm.from_dict(ast, strict="exact")
    document = tm.from_dict(ast, schema=schema, strict="exact")
    assert document.to_dict() == baseline.to_dict()
    assert document.to_markdown(canonical=True) == baseline.to_markdown(canonical=True)
    assert tm.from_markdown(document.to_markdown(canonical=True), schema=schema, html=html).to_dict() == tm.from_markdown(
        baseline.to_markdown(canonical=True), html=html,
    ).to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markdown", [
    ("## Notes\n\n> quote\n\n- first\n- second\n\n1. one\n2. two\n\n"
     "- [x] done\n- [ ] later\n\n| h | v |\n| --- | --- |\n| a | b |"),
    "| A |\n| --- |\n| |",
])
def test_native_markdown_with_unset_family_overlays_keeps_its_ast_and_written_bytes(html, markdown):
    schema = core_schema()
    baseline = tm.from_markdown(markdown, html=html)
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    assert parsed.to_dict() == baseline.to_dict()
    assert parsed.to_markdown(canonical=True) == baseline.to_markdown(canonical=True)
    copied = tm.from_dict(baseline.to_dict(), schema=schema, strict="exact")
    assert copied.to_markdown(canonical=True) == baseline.to_markdown(canonical=True)
