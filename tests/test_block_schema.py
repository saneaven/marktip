"""Block declarations compile their shapes, child sets and implicit wrappers."""

import json

import pytest

import marktip as tm


STRICT_LEVELS = ("content", "exact")


def doc(*children):
    return {"type": "doc", "content": list(children)}


def paragraph(value="x"):
    return {"type": "paragraph", "content": [{"type": "text", "text": value}]}


def details_nodes(*, content="summary body", **body_fields):
    fields = {"content": "paragraph+", "group": "", "implicit": True}
    fields.update(body_fields)
    return [
        tm.NodeSpec("details", kind="block", content=content),
        tm.NodeSpec("summary", kind="block", content="text*", group=""),
        tm.NodeSpec("body", kind="block", **fields),
    ]


@pytest.mark.parametrize("content", (None, "", "block+", "paragraph+", "text*", "inline*"))
def test_block_declarations_accept_atoms_containers_and_textblocks(content):
    declaration = tm.NodeSpec("custom", kind="block", content=content)
    assert declaration.implicit is False
    schema = tm.Schema(nodes=[declaration])
    assert schema.nodes == (declaration,)
    assert schema.to_dict()["nodes"][0]["content"] == content


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("parent", ("doc", "blockquote"))
@pytest.mark.parametrize("content, children", [
    (None, None),
    ("paragraph+", [paragraph()]),
    ("text*", [{"type": "text", "text": "title"}]),
])
def test_block_kind_defaults_to_the_core_block_child_set(level, parent, content, children):
    schema = tm.Schema(nodes=[tm.NodeSpec("custom", kind="block", content=content)])
    node = {"type": "custom"}
    if children is not None:
        node["content"] = children
    ast = doc(node) if parent == "doc" else doc({"type": "blockquote", "content": [node]})
    assert tm.from_dict(ast, schema=schema, strict=level).to_dict() == ast


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("group", ("widget", ""))
def test_explicit_block_groups_replace_the_kind_default(level, group):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("embed", kind="block", group=group),
        tm.NodeSpec("holder", kind="block", content="widget+" if group else "embed+"),
    ])
    ast = doc({"type": "holder", "content": [{"type": "embed"}]})
    assert tm.from_dict(ast, schema=schema, strict=level).to_dict() == ast

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc({"type": "embed"}), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == "content[0]"


@pytest.mark.parametrize("group", ("inline", "block inline", "widget inline"))
def test_block_nodes_cannot_join_the_builtin_inline_group(group):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("custom", kind="block", group=group)])


def test_block_content_resolves_forward_type_and_group_names():
    assert tm.Schema(nodes=[
        tm.NodeSpec("layout", kind="block", content="title panels+"),
        tm.NodeSpec("panel", kind="block", content="paragraph+", group="panels"),
        tm.NodeSpec("title", kind="block", content="text*", group=""),
    ])


@pytest.mark.parametrize("content", ("paragraph text*", "block | inline", "paragraph mention"))
def test_block_content_cannot_mix_inline_and_block_children(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("custom", kind="block", content=content),
            tm.NodeSpec("mention", kind="inline"),
        ])


def test_block_and_inline_nodes_share_the_type_and_tag_namespaces():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("custom", kind="block"), tm.NodeSpec("custom", kind="inline")])
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("panel", kind="block", tag="shared"),
                         tm.NodeSpec("label", kind="inline", tag="SHARED")])
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("note", tag="shared")],
                  nodes=[tm.NodeSpec("panel", kind="block", tag="shared")])


def test_block_schema_json_roundtrip_preserves_the_implicit_flag():
    schema = tm.Schema(nodes=[
        *details_nodes(),
        tm.NodeSpec("embed", kind="block", attrs={"url": tm.Attr(str, required=True)}),
    ])
    declaration = schema.to_dict()
    by_name = {node["name"]: node for node in declaration["nodes"]}
    assert by_name["body"]["implicit"] is True
    assert by_name["body"]["group"] == ""
    assert by_name["body"]["tag"] is None
    assert by_name["body"]["attrs"] == {}
    assert by_name["embed"]["implicit"] is False
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


def test_omitted_serialized_implicit_flag_defaults_to_false():
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", kind="block")])
    declaration = schema.to_dict()
    del declaration["nodes"][0]["implicit"]
    assert tm.Schema.from_dict(declaration) == schema


def test_implicit_is_part_of_schema_identity():
    implicit = tm.Schema(nodes=details_nodes())
    explicit = tm.Schema(nodes=details_nodes(implicit=False))
    assert implicit != explicit
    assert tm.Schema.from_dict(implicit.to_dict()) == implicit
    assert tm.Schema.from_dict(explicit.to_dict()) == explicit


def test_extend_adds_block_declarations_without_changing_the_base():
    base = tm.Schema(nodes=details_nodes())
    declaration = base.to_dict()
    embed = tm.NodeSpec("embed", kind="block", attrs={"url": tm.Attr(str)})
    extended = base.extend(nodes=[embed])
    assert extended == tm.Schema(nodes=[*details_nodes(), embed])
    assert extended.nodes[-1] is embed
    assert base.to_dict() == declaration


@pytest.mark.parametrize("implicit", (None, 0, 1, "yes"))
def test_implicit_requires_a_bool(implicit):
    with pytest.raises(TypeError):
        tm.Schema(nodes=details_nodes(implicit=implicit))


def test_implicit_wrapper_has_no_attrs_group_or_explicit_tag():
    schema = tm.Schema(nodes=details_nodes())
    body = schema.nodes[2]
    assert body.implicit is True
    assert body.attrs == {}
    assert body.group == ""
    assert body.tag is None


@pytest.mark.parametrize("fields", [
    {"group": None},
    {"group": "block"},
    {"group": "panels"},
    {"attrs": {"id": tm.Attr(str)}},
    {"attrs": {"id": tm.Attr(str, required=True)}},
    {"tag": "body"},
    {"tag": "content-wrapper"},
])
def test_implicit_wrapper_rejects_attrs_groups_and_explicit_tags(fields):
    with pytest.raises(ValueError):
        tm.Schema(nodes=details_nodes(**fields))


@pytest.mark.parametrize("content", (None, "", "text*", "inline*"))
def test_implicit_wrappers_require_block_content(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("layout", kind="block", content="body"),
            tm.NodeSpec("body", kind="block", content=content, group="", implicit=True),
        ])


@pytest.mark.parametrize("content", ("summary body", "summary? body", "body summary?"))
def test_implicit_wrapper_can_appear_once_between_optional_direct_children(content):
    assert tm.Schema(nodes=details_nodes(content=content))


@pytest.mark.parametrize("content", (
    "summary body?", "summary body*", "summary body+", "summary body{2}",
    "summary body body", "(summary body)+", "(summary body)?",
))
def test_implicit_wrapper_must_appear_exactly_once_without_optional_or_repeated_parents(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=details_nodes(content=content))


def test_implicit_wrapper_must_be_present_in_every_parent_alternative():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            *details_nodes(content="summary (body | divider)"),
            tm.NodeSpec("divider", kind="block", group=""),
        ])


@pytest.mark.parametrize("content", ("summary body paragraph", "summary body block*"))
def test_implicit_child_set_must_be_disjoint_from_direct_parent_children(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=details_nodes(content=content))


def test_implicit_wrapper_disjointness_resolves_custom_groups():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("layout", kind="block", content="title body panels*"),
            tm.NodeSpec("title", kind="block", content="text*", group=""),
            tm.NodeSpec("body", kind="block", content="panel+", group="", implicit=True),
            tm.NodeSpec("panel", kind="block", content="paragraph+", group="panels"),
        ])


def test_distinct_implicit_wrappers_can_accept_disjoint_child_sets():
    assert tm.Schema(nodes=[
        tm.NodeSpec("layout", kind="block", content="body rules"),
        tm.NodeSpec("body", kind="block", content="paragraph+", group="", implicit=True),
        tm.NodeSpec("rules", kind="block", content="horizontalRule+", group="", implicit=True),
    ])


def test_implicit_children_of_one_parent_cannot_accept_the_same_type():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("layout", kind="block", content="left right"),
            tm.NodeSpec("left", kind="block", content="paragraph+", group="", implicit=True),
            tm.NodeSpec("right", kind="block", content="paragraph+", group="", implicit=True),
        ])


def test_implicit_sibling_disjointness_resolves_custom_groups():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("layout", kind="block", content="left right"),
            tm.NodeSpec("left", kind="block", content="panel+", group="", implicit=True),
            tm.NodeSpec("right", kind="block", content="panels+", group="", implicit=True),
            tm.NodeSpec("panel", kind="block", content="paragraph+", group="panels"),
        ])


def test_implicit_wrappers_of_different_parents_can_accept_the_same_type():
    assert tm.Schema(nodes=[
        tm.NodeSpec("first", kind="block", content="left"),
        tm.NodeSpec("second", kind="block", content="right"),
        tm.NodeSpec("left", kind="block", content="paragraph+", group="", implicit=True),
        tm.NodeSpec("right", kind="block", content="paragraph+", group="", implicit=True),
    ])


@pytest.mark.parametrize("nodes", [
    [tm.NodeSpec("cycle", kind="block", content="cycle")],
    [tm.NodeSpec("first", kind="block", content="second"),
     tm.NodeSpec("second", kind="block", content="first")],
    [tm.NodeSpec("holder", kind="block", content="required"),
     tm.NodeSpec("required", kind="block", attrs={"id": tm.Attr(str, required=True)})],
])
def test_schema_can_declare_content_that_fill_cannot_create(nodes):
    schema = tm.Schema(nodes=nodes)
    assert schema.nodes == tuple(nodes)


def test_fill_cannot_choose_its_own_type_before_a_creatable_alternative():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("section", kind="block", content="(section | paragraph)+")])


def test_fill_can_choose_a_creatable_alternative_before_its_own_type():
    assert tm.Schema(nodes=[tm.NodeSpec("section", kind="block", content="(paragraph | section)+")])


def test_fill_cannot_create_an_indirect_cycle_through_preferred_alternatives():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("first", kind="block", content="second | paragraph"),
            tm.NodeSpec("second", kind="block", content="first", group=""),
        ])

