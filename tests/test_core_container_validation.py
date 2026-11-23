"""Core container tags share the dict rules and permit table forms that carry blocks."""

import pytest

import marktip as tm


STRICT_LEVELS = ("content", "exact")
LIST_TYPES = ("bulletList", "orderedList", "taskList", "listItem", "taskItem")
TABLE_TYPES = ("table", "tableRow", "tableHeader", "tableCell")
CONTAINER_TYPES = ("blockquote", *LIST_TYPES, *TABLE_TYPES)
CELL_CHILD_PATH = "content[0].content[0].content[0].content[0]"


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def text(value="x"):
    return {"type": "text", "text": value}


def p(value="x"):
    return node("paragraph", text(value))


def doc(*children):
    return {"type": "doc", "content": list(children)}


def container_case(owner, attrs):
    if owner == "blockquote":
        return doc(node(owner, p(), attrs=attrs)), "content[0]"
    if owner in LIST_TYPES:
        root = owner if owner in ("bulletList", "orderedList", "taskList") else (
            "taskList" if owner == "taskItem" else "bulletList"
        )
        item = "taskItem" if root == "taskList" else "listItem"
        root_attrs = {"tight": True}
        item_attrs = {"checked": False} if item == "taskItem" else {}
        if owner == root:
            root_attrs.update(attrs)
        else:
            item_attrs.update(attrs)
        ast = doc(node(root, node(item, p(), attrs=item_attrs), attrs=root_attrs))
        return ast, "content[0]" if owner == root else "content[0].content[0]"
    header = node("tableHeader", p())
    first_row = node("tableRow", header)
    cell = node("tableCell", p())
    second_row = node("tableRow", cell)
    table_attrs = {"colCount": 1}
    target = {"tableRow": second_row, "tableHeader": header, "tableCell": cell}
    if owner == "table":
        table_attrs.update(attrs)
    elif attrs:
        target[owner]["attrs"] = attrs
    paths = {"table": "content[0]", "tableRow": "content[0].content[1]",
             "tableHeader": "content[0].content[0].content[0]", "tableCell": "content[0].content[1].content[0]"}
    return doc(node("table", first_row, second_row, attrs=table_attrs)), paths[owner]


def error_from_dict(ast, schema, level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    return excinfo.value


def assert_error(error, code, field, path):
    assert (error.code, error.field, error.path) == (code, field, path)
    assert error.detail == str(error)


@pytest.mark.parametrize("owner", CONTAINER_TYPES)
@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_container_overlay_values_use_shared_rules_at_the_owner_location(owner, level):
    schema = tm.Schema(core_attrs={owner: {"tone": tm.Attr(str, choices=("note", "warning"))}})
    ast, path = container_case(owner, {"tone": "other"})
    assert_error(error_from_dict(ast, schema, level), "invalid_attr_value", "tone", path)


@pytest.mark.parametrize("owner", CONTAINER_TYPES)
def test_default_container_overlay_values_are_unset_and_keep_the_markdown_form(owner):
    schema = tm.Schema(core_attrs={owner: {"tone": tm.Attr(str, default="note")}})
    ast, _ = container_case(owner, {"tone": "note"})
    expected, _ = container_case(owner, {})
    if owner == "orderedList":
        expected["content"][0]["attrs"]["start"] = 1
    document = tm.from_dict(ast, schema=schema, strict="exact")
    assert document.to_dict() == expected
    assert document.to_markdown(canonical=True) == tm.from_dict(expected, strict="exact").to_markdown(canonical=True)


@pytest.mark.parametrize("owner, source", (
    ("blockquote", '<blockquote typo="x">\nx\n</blockquote>'),
    ("bulletList", '<ul typo="x">\n<li>\nx\n</li>\n</ul>'),
    ("orderedList", '<ol typo="x">\n<li>\nx\n</li>\n</ol>'),
    ("listItem", '<ul>\n<li typo="x">\nx\n</li>\n</ul>'),
    ("table", '<table typo="x">\n<tr>\n<th>\nx\n</th>\n</tr>\n</table>'),
    ("tableRow", '<table>\n<tr typo="x">\n<th>\nx\n</th>\n</tr>\n</table>'),
    ("tableHeader", '<table>\n<tr>\n<th typo="x">\nx\n</th>\n</tr>\n</table>'),
    ("tableCell", '<table>\n<tr>\n<td typo="x">\nx\n</td>\n</tr>\n</table>'),
))
def test_active_core_container_tags_refuse_unknown_attrs(owner, source):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=tm.Schema(core_attrs={owner: {}}))
    assert_error(excinfo.value, "unknown_attr", "typo", "")


@pytest.mark.parametrize("owner, source, field", (
    ("orderedList", '<ol type="a">\n<li>\nx\n</li>\n</ol>', "type"),
    ("tableCell", '<table>\n<tr>\n<td colwidth="100">\nx\n</td>\n</tr>\n</table>', "colwidth"),
))
def test_active_core_container_tags_refuse_undeclared_dropped_attrs(owner, source, field):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=tm.Schema(core_attrs={owner: {}}))
    assert_error(excinfo.value, "unknown_attr", field, "")


@pytest.mark.parametrize("cell_type", ("tableCell", "tableHeader"))
@pytest.mark.parametrize("field", ("colspan", "rowspan"))
@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("value, code", ((2, "unrepresentable"), ("2", "invalid_attr_value")))
def test_undeclared_cell_spans_keep_the_existing_dict_errors_when_the_table_family_is_active(
    cell_type, field, level, value, code,
):
    ast = doc(node("table", node("tableRow", node(cell_type, p(), attrs={field: value}))))
    baseline = error_from_dict(ast, tm.Schema(), level)
    active = error_from_dict(ast, tm.Schema(core_attrs={"table": {}}), level)
    path = "content[0].content[0].content[0]"
    assert_error(active, code, field, path)
    assert (active.code, active.field, active.path, str(active)) == (
        baseline.code, baseline.field, baseline.path, str(baseline),
    )


@pytest.mark.parametrize("tag", ("th", "td"))
@pytest.mark.parametrize("field", ("colspan", "rowspan"))
def test_undeclared_cell_spans_keep_the_span_rule_when_read_from_active_tags(tag, field):
    source = f'<table>\n<tr>\n<{tag} {field}="2">\nx\n</{tag}>\n</tr>\n</table>'
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=tm.Schema(core_attrs={"table": {}}))
    assert_error(excinfo.value, "unrepresentable", field, "")


@pytest.mark.parametrize("owner", ("tableCell", "tableHeader"))
@pytest.mark.parametrize("field, value, attr", (
    ("colspan", 2, tm.Attr(int)),
    ("rowspan", 2, tm.Attr(int)),
    ("colwidth", [100, 200], tm.Attr(tm.IntList)),
))
def test_declared_cell_spans_and_widths_are_carried_by_the_tag(owner, field, value, attr):
    schema = tm.Schema(core_attrs={owner: {field: attr}})
    ast = doc(node("table", node("tableRow", node(owner, p(), attrs={field: value}))))
    document = tm.from_dict(ast, schema=schema, strict="exact")
    expected = doc({**ast["content"][0], "attrs": {"colCount": 1}})
    assert document.to_dict() == expected
    written = document.to_markdown(canonical=True)
    rendered = "100,200" if field == "colwidth" else "2"
    assert f' {field}="{rendered}"' in written
    parsed = tm.from_markdown(written, schema=schema).to_dict()
    assert parsed["content"][0]["content"][0]["content"][0]["attrs"][field] == value


@pytest.mark.parametrize("cell_type", ("tableCell", "tableHeader"))
@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("multiple", (False, True))
def test_inactive_table_families_keep_the_declared_block_cell_refusals(cell_type, level, multiple):
    declarations = [tm.NodeSpec("callout", "block", content="paragraph+"), tm.NodeSpec("embed", "block")]
    children = [node("embed"), p("after")] if multiple else [node("callout", p())]
    ast = doc(node("table", node("tableRow", node(cell_type, *children))))
    baseline = error_from_dict(ast, tm.Schema(nodes=declarations), level)
    unrelated = error_from_dict(ast, tm.Schema(nodes=declarations, core_attrs={"blockquote": {}}), level)
    assert_error(unrelated, "unrepresentable", "content", CELL_CHILD_PATH)
    assert (unrelated.code, unrelated.field, unrelated.path, str(unrelated)) == (
        baseline.code, baseline.field, baseline.path, str(baseline),
    )


@pytest.mark.parametrize("owner", TABLE_TYPES)
@pytest.mark.parametrize("cell_type", ("tableCell", "tableHeader"))
@pytest.mark.parametrize("multiple", (False, True))
def test_any_active_table_owner_allows_block_cells_and_promotes_the_whole_table(owner, cell_type, multiple):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="paragraph+"),
                              tm.NodeSpec("embed", "block")], core_attrs={owner: {}})
    children = [node("embed"), p("after")] if multiple else [node("callout", p())]
    ast = doc(node("table", node("tableRow", node(cell_type, *children))))
    document = tm.from_dict(ast, schema=schema, strict="exact")
    expected = doc({**ast["content"][0], "attrs": {"colCount": 1}})
    assert document.to_dict() == expected
    written = document.to_markdown(canonical=True)
    assert written.startswith('<table colCount="1">')
    assert "<tr>" in written
    assert ("<th>" if cell_type == "tableHeader" else "<td>") in written
    assert tm.from_markdown(written, schema=schema).to_dict() == expected
