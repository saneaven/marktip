"""Core attr declarations use the same schema persistence and validation boundary."""

import json

import pytest

import marktip as tm


def test_empty_core_attrs_keep_the_default_schema_and_json_shape():
    default = tm.Schema()
    explicit = tm.Schema(core_attrs={})
    assert default.core_attrs == explicit.core_attrs == {}
    assert explicit == default
    assert hash(explicit) == hash(default)
    assert explicit.to_dict() == {"marks": []}
    assert tm.Schema.from_dict({"marks": []}) == explicit
    assert explicit.extend(core_attrs={}) == default


def test_default_core_attr_maps_are_not_shared_between_schemas():
    first = tm.Schema()
    second = tm.Schema()
    assert first.core_attrs == second.core_attrs == {}
    assert first.core_attrs is not second.core_attrs


@pytest.mark.parametrize("type_", ("paragraph", "heading", "image", "link"))
def test_single_core_nodes_and_link_accept_added_attrs(type_):
    attrs = {type_: {"data-label": tm.Attr(str)}}
    schema = tm.Schema(core_attrs=attrs)
    assert schema.core_attrs == attrs
    assert schema.to_dict()["core_attrs"][type_]["data-label"]["type"] == "str"


@pytest.mark.parametrize("type_", ("paragraph", "heading", "image", "link"))
def test_core_attrs_cannot_be_required(type_):
    with pytest.raises(ValueError):
        tm.Schema(core_attrs={type_: {"id": tm.Attr(str, required=True)}})


@pytest.mark.parametrize("type_, name, attr", (
    ("link", "target", tm.Attr(str, default="_blank")),
    ("link", "rel", tm.Attr(str)),
    ("link", "class", tm.Attr(str)),
    ("image", "width", tm.Attr(int, choices=(100, 200))),
    ("image", "height", tm.Attr(int)),
))
def test_dropped_core_attrs_can_be_replaced_by_tag_carried_declarations(type_, name, attr):
    schema = tm.Schema(core_attrs={type_: {name: attr}})
    assert schema.core_attrs[type_][name] is attr
    restored = tm.Schema.from_dict(json.loads(json.dumps(schema.to_dict())))
    assert restored == schema
    assert hash(restored) == hash(schema)


@pytest.mark.parametrize("type_, name", (
    ("heading", "level"),
    ("image", "src"),
    ("image", "alt"),
    ("image", "title"),
    ("link", "href"),
    ("link", "title"),
))
def test_markdown_carried_core_attrs_cannot_be_redeclared(type_, name):
    with pytest.raises(ValueError):
        tm.Schema(core_attrs={type_: {name: tm.Attr(str)}})


@pytest.mark.parametrize("type_", (
    "doc", "text", "htmlInline", "htmlBlock", "codeBlock", "hardBreak", "horizontalRule",
    "bold", "italic", "strike", "code", "missing",
))
def test_core_attrs_require_a_core_type_with_a_tag_form(type_):
    with pytest.raises(ValueError):
        tm.Schema(core_attrs={type_: {"data-label": tm.Attr(str)}})


def test_core_attrs_cannot_target_a_declared_node_or_mark():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("mention", kind="inline")],
                  core_attrs={"mention": {"id": tm.Attr(str)}})
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("underline", tag="u")],
                  core_attrs={"underline": {"id": tm.Attr(str)}})


@pytest.mark.parametrize("core_attrs", (
    [],
    1,
    {1: {"label": tm.Attr(str)}},
    {"paragraph": []},
    {"paragraph": {1: tm.Attr(str)}},
    {"paragraph": {"label": tm.Attr(float)}},
))
def test_wrong_core_attr_declaration_types_are_type_errors(core_attrs):
    with pytest.raises(TypeError):
        tm.Schema(core_attrs=core_attrs)


def test_core_attr_declarations_are_read_without_a_declaration_class_check():
    with pytest.raises(AttributeError):
        tm.Schema(core_attrs={"paragraph": {"label": str}})


@pytest.mark.parametrize("name, attr", (
    ("data label", tm.Attr(str)),
    ("label", tm.Attr(str, choices=("left", "right"), default="center")),
    ("label", tm.Attr(str, required=True, default="")),
    ("label", tm.Attr(int, uri="link")),
))
def test_core_attrs_use_the_shared_attr_declaration_rules(name, attr):
    with pytest.raises(ValueError):
        tm.Schema(core_attrs={"paragraph": {name: attr}})


def test_core_attrs_survive_json_alongside_marks_nodes_and_allowed_attr_fields():
    schema = tm.Schema(
        marks=[tm.MarkSpec("underline", tag="u")],
        nodes=[tm.NodeSpec("mention", kind="inline")],
        core_attrs={
            "paragraph": {
                "textAlign": tm.Attr(str, choices=("left", "center", "right"), default="left"),
                "count": tm.Attr(int, choices=(0, 1), default=0),
                "enabled": tm.Attr(bool, default=False),
                "source": tm.Attr(str, uri="link"),
            },
            "image": {"width": tm.Attr(int)},
            "link": {"target": tm.Attr(str, default="_blank")},
        },
    )
    declaration = schema.to_dict()
    paragraph = declaration["core_attrs"]["paragraph"]
    assert list(paragraph) == ["textAlign", "count", "enabled", "source"]
    assert paragraph["textAlign"]["choices"] == ["left", "center", "right"]
    assert paragraph["enabled"]["default"] is False
    assert paragraph["source"]["uri"] == "link"
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


def test_core_attr_maps_are_snapshotted_while_attr_declarations_remain_shared():
    attr = tm.Attr(str)
    attrs = {"id": attr}
    core_attrs = {"paragraph": attrs}
    schema = tm.Schema(core_attrs=core_attrs)
    before = schema.to_dict()
    expected = tm.Schema(core_attrs={"paragraph": {"id": attr}})

    attrs["id"] = tm.Attr(int)
    attrs["label"] = tm.Attr(str)
    core_attrs["image"] = {"width": tm.Attr(int)}
    del core_attrs["paragraph"]

    assert schema.core_attrs == {"paragraph": {"id": attr}}
    assert schema.core_attrs["paragraph"]["id"] is attr
    assert schema.to_dict() == before
    assert schema.extend() == expected
    extended = schema.extend(core_attrs={"paragraph": {"label": tm.Attr(str)}})
    assert extended.core_attrs == {"paragraph": {"id": attr, "label": tm.Attr(str)}}
    with pytest.raises(ValueError):
        schema.extend(core_attrs={"paragraph": {"id": tm.Attr(str)}})


def test_core_attr_identity_includes_the_type_attr_rules_and_attr_order():
    empty = tm.Schema()
    active = tm.Schema(core_attrs={"paragraph": {}})
    assert active != empty
    assert tm.Schema.from_dict(active.to_dict()) == active
    assert tm.Schema(core_attrs={"paragraph": {"label": tm.Attr(str)}}) != tm.Schema(
        core_attrs={"heading": {"label": tm.Attr(str)}}
    )
    assert tm.Schema(core_attrs={"paragraph": {"label": tm.Attr(str)}}) != tm.Schema(
        core_attrs={"paragraph": {"label": tm.Attr(str, default="")}}
    )
    assert tm.Schema(core_attrs={"paragraph": {"label": tm.Attr(str), "count": tm.Attr(int)}}) != tm.Schema(
        core_attrs={"paragraph": {"count": tm.Attr(int), "label": tm.Attr(str)}}
    )


def test_extend_merges_disjoint_core_attrs_and_keeps_the_base_declarations():
    base = tm.Schema(marks=[tm.MarkSpec("underline", tag="u")],
                     nodes=[tm.NodeSpec("mention", kind="inline")],
                     core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})
    before = base.to_dict()
    extended = base.extend(core_attrs={
        "paragraph": {"id": tm.Attr(str)},
        "link": {"target": tm.Attr(str, default="_blank")},
    })
    expected = tm.Schema(marks=base.marks, nodes=base.nodes, core_attrs={
        "paragraph": {"textAlign": tm.Attr(str), "id": tm.Attr(str)},
        "link": {"target": tm.Attr(str, default="_blank")},
    })
    assert extended == expected
    assert hash(extended) == hash(expected)
    assert list(extended.core_attrs["paragraph"]) == ["textAlign", "id"]
    assert base.to_dict() == before
    assert base.extend() == base
    with pytest.raises(ValueError):
        base.extend(core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})


def test_serialized_core_attrs_use_the_same_builder_rejections():
    declaration = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}}).to_dict()
    declaration["core_attrs"]["link"]["href"] = declaration["core_attrs"]["link"].pop("target")
    with pytest.raises(ValueError):
        tm.Schema.from_dict(declaration)
