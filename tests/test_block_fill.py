"""Markdown fills required children while the dict boundary only validates."""

import pytest

import marktip as tm


def document(*blocks):
    return {"type": "doc", "content": list(blocks)}


def paragraph(value=None):
    node = {"type": "paragraph"}
    if value is not None:
        node["content"] = [{"type": "text", "text": value}]
    return node


@pytest.mark.parametrize("html", [True, False])
def test_an_empty_container_fills_its_required_paragraph(html):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="paragraph+")])
    ast = document({"type": "callout", "content": [paragraph()]})
    markdown = tm.from_dict(ast, schema=schema).to_markdown(canonical=True)
    assert markdown == "<callout>\n\n</callout>"
    assert tm.from_markdown(markdown, schema=schema, html=html).to_dict() == ast


def test_fill_inserts_missing_children_without_replacing_existing_ones():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content="cap paragraph+ tail"),
        tm.NodeSpec("cap", "block", group=""),
        tm.NodeSpec("tail", "block", group=""),
    ])
    markdown = "<holder>\n\nbody\n\n</holder>"
    expected = document({"type": "holder", "content": [
        {"type": "cap"}, paragraph("body"), {"type": "tail"},
    ]})
    doc = tm.from_markdown(markdown, schema=schema)
    assert doc.to_dict() == expected
    assert tm.from_markdown(doc.to_markdown(canonical=True), schema=schema).to_dict() == expected


def test_fill_can_insert_between_existing_children():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content="paragraph cap paragraph"),
        tm.NodeSpec("cap", "block", group=""),
    ])
    markdown = "<holder>\n\nfirst\n\nsecond\n\n</holder>"
    expected = document({"type": "holder", "content": [
        paragraph("first"), {"type": "cap"}, paragraph("second"),
    ]})
    assert tm.from_markdown(markdown, schema=schema).to_dict() == expected


@pytest.mark.parametrize("expression, chosen", [("first | second", "first"), ("second | first", "second")])
def test_fill_prefers_the_first_type_named_in_the_expression(expression, chosen):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content=expression),
        tm.NodeSpec("first", "block", group=""),
        tm.NodeSpec("second", "block", group=""),
    ])
    ast = document({"type": "holder", "content": [{"type": chosen}]})
    assert tm.from_markdown("<holder>\n\n</holder>", schema=schema).to_dict() == ast


def test_fill_can_create_a_nested_minimal_content_tree():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content="panel"),
        tm.NodeSpec("panel", "block", content="paragraph+", group=""),
    ])
    expected = document({"type": "holder", "content": [
        {"type": "panel", "content": [paragraph()]},
    ]})
    assert tm.from_markdown("<holder>\n\n</holder>", schema=schema).to_dict() == expected


def test_nested_fill_prefers_the_first_type_after_creatable_types_are_known():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("outer", "block", content="holder"),
        tm.NodeSpec("holder", "block", content="panel | embed", group=""),
        tm.NodeSpec("panel", "block", content="paragraph+", group=""),
        tm.NodeSpec("embed", "block", group=""),
    ])
    expected = document({"type": "outer", "content": [{
        "type": "holder", "content": [{"type": "panel", "content": [paragraph()]}],
    }]})
    assert tm.from_markdown("<outer>\n\n</outer>", schema=schema).to_dict() == expected


def test_a_new_implicit_wrapper_fills_its_own_required_children():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content="body"),
        tm.NodeSpec("body", "block", content="paragraph cap", group="", implicit=True),
        tm.NodeSpec("cap", "block", group=""),
    ])
    expected = document({"type": "holder", "content": [{
        "type": "body", "content": [paragraph("body"), {"type": "cap"}],
    }]})
    assert tm.from_markdown("<holder>\n\nbody\n\n</holder>", schema=schema).to_dict() == expected


@pytest.mark.parametrize("content", ["heading", "horizontalRule", "codeBlock", "blockquote"])
def test_only_paragraph_can_be_created_among_core_block_types(content):
    schema = tm.Schema(nodes=[tm.NodeSpec("holder", "block", content=content)])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("<holder>\n\n</holder>", schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_content", "content", "content[0]")


def test_a_required_attr_prevents_creation():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content="embed"),
        tm.NodeSpec("embed", "block", group="", attrs={"id": tm.Attr(str, required=True)}),
    ])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("<holder>\n\n</holder>", schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_content", "content", "content[0]")


def test_required_content_cycles_cannot_be_created():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("holder", "block", content="first"),
        tm.NodeSpec("first", "block", content="second", group=""),
        tm.NodeSpec("second", "block", content="first", group=""),
    ])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("<holder>\n\n</holder>", schema=schema)
    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.path == "content[0]"


def test_fill_does_not_remove_a_child_that_the_expression_refuses():
    schema = tm.Schema(nodes=[tm.NodeSpec("holder", "block", content="paragraph+")])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("<holder>\n\n---\n\n</holder>", schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_content", "content", "content[0]")
