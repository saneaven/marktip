"""The dict boundary checks declared block shapes without filling them."""

import pytest

import marktip as tm


@pytest.fixture
def schema():
    return tm.Schema(nodes=[
        tm.NodeSpec("embed", "block", attrs={"id": tm.Attr(str, required=True)}),
        tm.NodeSpec("callout", "block", content="paragraph+"),
        tm.NodeSpec("summary", "block", content="inline*"),
    ])


def document(*blocks):
    return {"type": "doc", "content": list(blocks)}


@pytest.mark.parametrize("strict", ["content", "exact"])
@pytest.mark.parametrize("type", ["embed", "callout", "summary"])
def test_declared_blocks_refuse_a_marks_field(schema, strict, type):
    node = {"type": type, "marks": []}
    if type == "embed":
        node["attrs"] = {"id": "one"}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(document(node), schema=schema, strict=strict)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("unknown_field", "marks", "content[0]")


@pytest.mark.parametrize("strict", ["content", "exact"])
@pytest.mark.parametrize("children", [None, [], [{"type": "horizontalRule"}]])
def test_dict_content_is_checked_without_fill(schema, strict, children):
    node = {"type": "callout"}
    if children is not None:
        node["content"] = children
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(document({"type": "paragraph"}, node), schema=schema, strict=strict)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_content", "content", "content[1]")


@pytest.mark.parametrize("strict", ["content", "exact"])
def test_textblock_children_follow_the_content_expression(schema, strict):
    ast = document({"type": "summary", "content": [{"type": "paragraph"}]})
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=strict)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_content", "content", "content[0]")


@pytest.mark.parametrize("cell_type", ["tableCell", "tableHeader"])
@pytest.mark.parametrize("strict", ["content", "exact"])
def test_block_container_directly_in_a_table_cell_is_unrepresentable(schema, cell_type, strict):
    node = {"type": "callout", "content": [{"type": "paragraph"}]}
    ast = document({"type": "table", "content": [{"type": "tableRow", "content": [{
        "type": cell_type, "content": [node],
    }]}]})
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=strict)
    error = excinfo.value
    assert (error.code, error.field, error.path) == (
        "unrepresentable", "content", "content[0].content[0].content[0].content[0]",
    )


@pytest.mark.parametrize("cell_type", ["tableCell", "tableHeader"])
@pytest.mark.parametrize("strict", ["content", "exact"])
@pytest.mark.parametrize("type", ["embed", "summary"])
@pytest.mark.parametrize("position", [0, 1])
def test_a_declared_block_must_be_the_only_child_of_a_table_cell(schema, cell_type, strict, type, position):
    block = {"type": "embed", "attrs": {"id": "one"}} if type == "embed" else {
        "type": "summary", "content": [{"type": "text", "text": "title"}],
    }
    children = [{"type": "paragraph", "content": [{"type": "text", "text": "x"}]}]
    children.insert(position, block)
    ast = document({"type": "table", "content": [{"type": "tableRow", "content": [{
        "type": cell_type, "content": children,
    }]}]})
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=strict)
    error = excinfo.value
    assert (error.code, error.field, error.path) == (
        "unrepresentable", "content", f"content[0].content[0].content[0].content[{position}]",
    )
    assert tm.from_dict(ast, schema=schema, strict="off").to_dict() == ast


def test_off_skips_block_content_and_marks_checks(schema):
    ast = document({"type": "callout", "marks": [{"type": "bold"}]})
    assert tm.from_dict(ast, schema=schema, strict="off").to_dict() == ast


@pytest.mark.parametrize("entrypoint", ["dict", "markdown"])
def test_rejected_block_types_are_schema_names(schema, entrypoint):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if entrypoint == "dict":
            tm.from_dict(document({"type": "embed", "attrs": {"id": "one"}}),
                         schema=schema, reject_node_types=("embed",))
        else:
            tm.from_markdown('<embed id="one"/>', schema=schema, reject_node_types=("embed",))
    assert excinfo.value.code == "disallowed_node_type"
    assert excinfo.value.path == "content[0]"


@pytest.mark.parametrize("entrypoint", ["dict", "markdown"])
def test_declared_block_uri_attrs_obey_the_policy(entrypoint):
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", attrs={"url": tm.Attr(str, uri="link")})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if entrypoint == "dict":
            tm.from_dict(document({"type": "embed", "attrs": {"url": "http://example.com"}}),
                         schema=schema, link_schemes=("https",))
        else:
            tm.from_markdown('<embed url="http://example.com"/>', schema=schema, link_schemes=("https",))
    assert excinfo.value.code == "disallowed_scheme"
    assert excinfo.value.field == "url"
    assert excinfo.value.path == "content[0]"


@pytest.mark.parametrize("html", [True, False])
@pytest.mark.parametrize("source, path", [
    ("<callout>\n\nbody", ""),
    ("</callout>", ""),
    ("<callout/>", ""),
    ('</embed>', ""),
    ('before <embed id="one"/> after', "content[0]"),
    ("<summary>title", "content[0]"),
    ("title</summary>", "content[0]"),
    ("<summary/>title</summary>", "content[0]"),
    ("before <summary>title</summary>", "content[0]"),
    ("<summary>title</summary> after", "content[0]"),
    ("> <callout>\n>\n> body", "content[0]"),
])
def test_block_carriers_must_have_their_declared_shape(schema, html, source, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=schema, html=html)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_tag", "content", path)


def test_block_containers_must_close_in_the_same_parent(schema):
    source = "<callout>\n\n> body\n>\n> </callout>"
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_tag", "content", "")


def test_block_containers_must_be_properly_nested():
    schema = tm.Schema(nodes=[tm.NodeSpec("outer", "block", content="block*"),
                              tm.NodeSpec("inner", "block", content="block*")])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("<outer>\n<inner>\n</outer>\n</inner>", schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_tag", "content", "")


@pytest.mark.parametrize("shape, content, source, path", [
    ("atom", None, '<sample unknown="x"/>', ""),
    ("container", "block*", '<sample unknown="x">\n\n</sample>', ""),
    ("textblock", "inline*", '<sample unknown="x">title</sample>', "content[0]"),
])
def test_unknown_attrs_on_each_block_carrier_are_located(shape, content, source, path):
    schema = tm.Schema(nodes=[tm.NodeSpec("sample", "block", content=content)])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("unknown_attr", "unknown", path)


@pytest.mark.parametrize("source, code, field", [
    ("<embed/>", "missing_attr", "id"),
    ('<embed id="one" id="two"/>', "invalid_attr_value", "id"),
    ('<embed id="one" count="many"/>', "invalid_attr_value", "count"),
    ('<embed id="one" checked="yes"/>', "invalid_attr_value", "checked"),
    ('<embed id="one" tone="other"/>', "invalid_attr_value", "tone"),
])
def test_lifted_block_attrs_use_the_shared_rules(source, code, field):
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", attrs={
        "id": tm.Attr(str, required=True), "count": tm.Attr(int), "checked": tm.Attr(bool),
        "tone": tm.Attr(str, choices=("info", "warning")),
    })])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == (code, field, "")
