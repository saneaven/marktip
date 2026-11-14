"""Fence and math carriers extend plain node declarations."""

from dataclasses import FrozenInstanceError
import json

import pytest

import marktip as tm


def carrier_node(carrier, **fields):
    declaration = {"attrs": {"latex": tm.Attr(str)}, "body": "latex"}
    declaration.update(fields)
    if carrier == "fence":
        return tm.NodeSpec("formula", kind="block", fence="math", **declaration)
    return tm.NodeSpec("formula", kind="inline" if carrier == "inline" else "block",
                       math=carrier, **declaration)


def test_carrier_declarations_are_frozen_plain_data_with_none_defaults():
    node = tm.NodeSpec("mention", kind="inline")
    assert node.fence is node.math is node.body is None
    with pytest.raises(FrozenInstanceError):
        node.fence = "math"
    with pytest.raises(FrozenInstanceError):
        node.math = "inline"
    with pytest.raises(FrozenInstanceError):
        node.body = "latex"


@pytest.mark.parametrize("carrier", ["fence", "inline", "display"])
@pytest.mark.parametrize("required", [False, True])
def test_each_carrier_accepts_its_atom_shape_and_a_declared_str_body(carrier, required):
    node = carrier_node(carrier, attrs={"latex": tm.Attr(str, required=required)})
    nodes = (node,)
    schema = tm.Schema(nodes=nodes)
    assert schema.nodes is nodes
    assert schema.nodes[0].body == "latex"
    assert schema.nodes[0].attrs is node.attrs


def test_a_display_atom_can_also_declare_a_fence():
    node = tm.NodeSpec("formula", kind="block", tag="equation", fence="math", math="display",
                       body="latex", attrs={"latex": tm.Attr(str)})
    schema = tm.Schema(nodes=[node])
    assert schema.nodes == (node,)
    declaration = schema.to_dict()["nodes"][0]
    assert declaration["tag"] == "equation"
    assert declaration["fence"] == "math"
    assert declaration["math"] == "display"
    assert declaration["body"] == "latex"


def test_a_body_without_an_additional_carrier_keeps_the_tag_declaration():
    node = tm.NodeSpec("formula", kind="block", body="latex", attrs={"latex": tm.Attr(str)})
    schema = tm.Schema(nodes=[node])
    assert schema.nodes[0].fence is None
    assert schema.nodes[0].math is None
    assert schema.to_dict()["nodes"][0]["body"] == "latex"


@pytest.mark.parametrize("carrier", ["fence", "inline", "display"])
def test_carriers_require_a_body_name(carrier):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[carrier_node(carrier, body=None)])


@pytest.mark.parametrize("carrier", ["fence", "inline", "display"])
def test_the_body_name_must_refer_to_a_declared_attr(carrier):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[carrier_node(carrier, body="missing")])


@pytest.mark.parametrize("carrier", ["fence", "inline", "display"])
@pytest.mark.parametrize("type_", [int, bool])
def test_the_body_attr_must_be_a_str(carrier, type_):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[carrier_node(carrier, attrs={"latex": tm.Attr(type_)})])


@pytest.mark.parametrize("type_", [int, bool])
def test_a_body_without_a_carrier_still_requires_a_declared_str_attr(type_):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("formula", kind="block", body="latex",
                                     attrs={"latex": tm.Attr(type_)})])


@pytest.mark.parametrize("kind, content", [
    ("inline", None),
    ("inline", "text*"),
    ("block", "paragraph*"),
    ("block", "inline*"),
])
def test_fences_are_only_available_on_block_atoms(kind, content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("formula", kind=kind, content=content, fence="math", body="latex",
                                     attrs={"latex": tm.Attr(str)})])


@pytest.mark.parametrize("kind, content", [
    ("block", None),
    ("inline", "text*"),
    ("block", "paragraph*"),
    ("block", "inline*"),
])
def test_inline_math_is_only_available_on_inline_atoms(kind, content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("formula", kind=kind, content=content, math="inline", body="latex",
                                     attrs={"latex": tm.Attr(str)})])


@pytest.mark.parametrize("kind, content", [
    ("inline", None),
    ("inline", "text*"),
    ("block", "paragraph*"),
    ("block", "inline*"),
])
def test_display_math_is_only_available_on_block_atoms(kind, content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("formula", kind=kind, content=content, math="display", body="latex",
                                     attrs={"latex": tm.Attr(str)})])


@pytest.mark.parametrize("mode", ["", "block", "INLINE"])
def test_unknown_math_modes_are_value_errors(mode):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("formula", kind="block", math=mode, body="latex",
                                     attrs={"latex": tm.Attr(str)})])


@pytest.mark.parametrize("field, value", [("fence", 1), ("math", True), ("body", 1)])
def test_carrier_fields_of_the_wrong_python_type_are_type_errors(field, value):
    fields = {"fence": "math", "body": "latex", "attrs": {"latex": tm.Attr(str)}}
    fields[field] = value
    with pytest.raises(TypeError):
        tm.Schema(nodes=[tm.NodeSpec("formula", kind="block", **fields)])


def test_two_types_cannot_share_a_fence_word():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("first", kind="block", fence="math", body="latex", attrs={"latex": tm.Attr(str)}),
            tm.NodeSpec("second", kind="block", fence="math", body="latex", attrs={"latex": tm.Attr(str)}),
        ])


@pytest.mark.parametrize("mode", ["inline", "display"])
def test_two_types_cannot_share_a_math_mode(mode):
    kind = "inline" if mode == "inline" else "block"
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("first", kind=kind, math=mode, body="latex", attrs={"latex": tm.Attr(str)}),
            tm.NodeSpec("second", kind=kind, math=mode, body="latex", attrs={"latex": tm.Attr(str)}),
        ])


def test_distinct_fence_words_and_math_modes_can_share_one_schema():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("blockMath", kind="block", fence="math", math="display", body="latex",
                    attrs={"latex": tm.Attr(str)}),
        tm.NodeSpec("diagram", kind="block", fence="diagram", body="source", attrs={"source": tm.Attr(str)}),
        tm.NodeSpec("inlineMath", kind="inline", math="inline", body="latex", attrs={"latex": tm.Attr(str)}),
    ])
    assert len(schema.nodes) == 3


def test_carrier_fields_survive_json_roundtrip_and_keep_the_tag_form():
    schema = tm.Schema(nodes=[
        tm.NodeSpec("blockMath", kind="block", tag="equation", fence="math", math="display", body="latex",
                    attrs={"latex": tm.Attr(str, required=True), "label": tm.Attr(str)}),
        tm.NodeSpec("inlineMath", kind="inline", tag="inline-equation", math="inline", body="latex",
                    attrs={"latex": tm.Attr(str)}),
    ])
    declaration = schema.to_dict()
    first, second = declaration["nodes"]
    assert (first["fence"], first["math"], first["body"], first["tag"]) == (
        "math", "display", "latex", "equation",
    )
    assert (second["fence"], second["math"], second["body"], second["tag"]) == (
        None, "inline", "latex", "inline-equation",
    )
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


def test_omitted_serialized_carrier_fields_default_to_none():
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", kind="block")])
    declaration = schema.to_dict()
    for field in ("fence", "math", "body"):
        del declaration["nodes"][0][field]
    assert tm.Schema.from_dict(declaration) == schema


@pytest.mark.parametrize("field, first, second, kind", [
    ("fence", None, "math", "block"),
    ("math", None, "inline", "inline"),
    ("body", "latex", "source", "block"),
])
def test_carrier_fields_are_part_of_schema_identity(field, first, second, kind):
    fields = {"body": "latex", "attrs": {"latex": tm.Attr(str), "source": tm.Attr(str)}}
    first_fields = {**fields, field: first}
    second_fields = {**fields, field: second}
    first_schema = tm.Schema(nodes=[tm.NodeSpec("formula", kind=kind, **first_fields)])
    second_schema = tm.Schema(nodes=[tm.NodeSpec("formula", kind=kind, **second_fields)])
    assert first_schema != second_schema
    assert tm.Schema.from_dict(first_schema.to_dict()) == first_schema
    assert tm.Schema.from_dict(second_schema.to_dict()) == second_schema


def test_extend_preserves_carrier_declarations_and_refuses_collisions():
    block = tm.NodeSpec("blockMath", kind="block", fence="math", body="latex", attrs={"latex": tm.Attr(str)})
    base = tm.Schema(nodes=[block])
    before = base.to_dict()
    inline = tm.NodeSpec("inlineMath", kind="inline", math="inline", body="latex", attrs={"latex": tm.Attr(str)})
    display = tm.NodeSpec("displayMath", kind="block", math="display", body="latex", attrs={"latex": tm.Attr(str)})
    extended = base.extend(nodes=[inline, display])
    expected = tm.Schema(nodes=[block, inline, display])
    assert extended == expected
    assert hash(extended) == hash(expected)
    assert extended.nodes[-2:] == (inline, display)
    assert base.to_dict() == before
    with pytest.raises(ValueError):
        base.extend(nodes=[tm.NodeSpec("other", kind="block", fence="math", body="source",
                                      attrs={"source": tm.Attr(str)})])
    with pytest.raises(ValueError):
        extended.extend(nodes=[tm.NodeSpec("other", kind="inline", math="inline", body="source",
                                          attrs={"source": tm.Attr(str)})])
