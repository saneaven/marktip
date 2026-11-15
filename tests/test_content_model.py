"""Strict mode closes ProseMirror fields and per-node content expressions."""

import pytest

import marktip as tm


LEVELS = ("content", "exact")


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x", **extra):
    return {"type": "text", "text": value, **extra}


@pytest.mark.parametrize("level", LEVELS)
def test_unknown_node_field_is_rejected_at_the_nested_node(level):
    ast = doc(p(text("x", arbitrary={"nested": True})))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    err = excinfo.value
    assert err.code == "unknown_field"
    assert err.field == "arbitrary"
    assert err.path == "content[0].content[0]"
    assert str(err) == "field 'arbitrary' is not defined for node type 'text'"


@pytest.mark.parametrize("level", LEVELS)
def test_unknown_mark_field_is_rejected_at_the_mark(level):
    ast = doc(p(text("x", marks=[{"type": "bold", "priority": 1}])))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    err = excinfo.value
    assert err.code == "unknown_field"
    assert err.field == "priority"
    assert err.path == "content[0].content[0].marks[0]"
    assert str(err) == "field 'priority' is not defined for mark type 'bold'"


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "ast, path",
    [
        (doc(text()), "content[0]"),
        (doc(p(p(text()))), "content[0].content[0]"),
        (
            doc({"type": "codeBlock", "content": [{"type": "hardBreak"}]}),
            "content[0].content[0]",
        ),
        (
            doc({"type": "bulletList", "content": [{"type": "taskItem", "content": [p(text())]}]}),
            "content[0].content[0]",
        ),
        (
            doc({"type": "taskList", "content": [{"type": "listItem", "content": [p(text())]}]}),
            "content[0].content[0]",
        ),
        (doc({"type": "table", "content": [p(text())]}), "content[0].content[0]"),
        (
            doc({"type": "table", "content": [{"type": "tableRow", "content": [p(text())]}]}),
            "content[0].content[0].content[0]",
        ),
    ],
)
def test_invalid_parent_child_relationship_is_rejected(level, ast, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    err = excinfo.value
    assert err.code == "invalid_content"
    assert err.field == "content"
    assert err.path == path


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("leaf", ["text", "hardBreak", "horizontalRule", "image", "htmlBlock", "htmlInline"])
def test_leaf_nodes_cannot_carry_content(level, leaf):
    node = {"type": leaf, "content": []}
    if leaf == "text":
        node["text"] = "x"
    if leaf == "image":
        node["attrs"] = {"src": "x.png"}
    if leaf.startswith("html"):
        node["attrs"] = {"html": "<u>x</u>"}
    ast = doc(p(node)) if leaf in {"text", "hardBreak", "image", "htmlInline"} else doc(node)

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "content"


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("value", [None, 1, ""])
def test_text_payload_must_be_a_nonempty_string(level, value):
    node = {"type": "text"}
    if value is not None:
        node["text"] = value
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(p(node)), strict=level)

    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "text"
    assert excinfo.value.path == "content[0].content[0]"


@pytest.mark.parametrize("level", LEVELS)
def test_code_block_text_cannot_carry_marks(level):
    ast = doc(
        {
            "type": "codeBlock",
            "content": [{"type": "text", "text": "x", "marks": [{"type": "bold"}]}],
        }
    )
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "marks"
    assert excinfo.value.path == "content[0].content[0]"


@pytest.mark.parametrize("level", LEVELS)
def test_ordered_list_accepts_the_task_item_shape_emitted_by_the_parser(level):
    parsed = tm.from_markdown("1. [x] done\n")

    converted = tm.from_dict(parsed.to_dict(), strict=level)

    assert converted.to_markdown(canonical=True) == parsed.to_markdown(canonical=True) == "1. [x] done"


@pytest.mark.parametrize("level", LEVELS)
def test_block_nodes_cannot_carry_marks_or_text_fields(level):
    with pytest.raises(tm.InvalidNodeError) as marks_error:
        tm.from_dict(doc({"type": "paragraph", "marks": []}), strict=level)
    assert marks_error.value.code == "unknown_field"
    assert marks_error.value.field == "marks"

    with pytest.raises(tm.InvalidNodeError) as text_error:
        tm.from_dict(doc({"type": "paragraph", "text": "lost"}), strict=level)
    assert text_error.value.code == "unknown_field"
    assert text_error.value.field == "text"


def test_strict_off_retains_the_converter_compatibility_surface():
    ast = doc(p({"type": "text", "text": "x", "arbitrary": True}, p(text("flattened"))))
    converted = tm.from_dict(ast)
    assert converted.to_markdown(canonical=True) == "xflattened"
    assert "arbitrary" not in converted.to_dict()["content"][0]["content"][0]
