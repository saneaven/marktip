"""Inline node declarations compile through the same schema boundary as marks."""

from dataclasses import FrozenInstanceError, is_dataclass
import json

import pytest

import marktip as tm


def test_node_declarations_are_frozen_plain_dataclasses():
    node = tm.NodeSpec("mention", kind="inline")
    assert is_dataclass(node)
    assert node.name == "mention"
    assert node.kind == "inline"
    assert node.content is node.group is node.tag is None
    assert node.attrs == {}
    with pytest.raises(FrozenInstanceError):
        node.kind = "block"
    assert tm.NodeSpec("first", kind="inline").attrs is not tm.NodeSpec("second", kind="inline").attrs

    invalid = tm.NodeSpec("mention", kind="inline", attrs={"id": tm.Attr(float)})
    with pytest.raises(TypeError):
        tm.Schema(nodes=[invalid])


def test_nodes_are_kept_in_the_given_tuple_without_changing_the_empty_json_shape():
    nodes = (tm.NodeSpec("mention", kind="inline"),)
    schema = tm.Schema(nodes=nodes)
    assert schema.nodes is nodes
    assert schema.marks == ()
    assert tm.Schema().nodes == ()
    assert tm.Schema().to_dict() == {"marks": []}
    assert tm.Schema.from_dict({"marks": []}).nodes == ()


def test_schema_json_roundtrip_preserves_all_node_declaration_fields():
    schema = tm.Schema(
        marks=[tm.MarkSpec("underline", tag="u")],
        nodes=[
            tm.NodeSpec("mention", kind="inline", tag="user", group="inline symbol", attrs={
                "id": tm.Attr(str, required=True),
                "label": tm.Attr(str, choices=("one", "two"), default="one"),
                "count": tm.Attr(int, choices=(-1, 0, 2), default=0),
                "enabled": tm.Attr(bool, choices=(False, True), default=False),
                "url": tm.Attr(str, uri="link"),
                "image": tm.Attr(str, uri="image"),
            }),
            tm.NodeSpec("label", kind="inline", content="(text | mention)*", group=""),
        ],
    )
    declaration = schema.to_dict()
    assert list(declaration) == ["marks", "nodes"]
    assert [node["name"] for node in declaration["nodes"]] == ["mention", "label"]
    assert declaration["nodes"][0]["kind"] == "inline"
    assert declaration["nodes"][0]["group"] == "inline symbol"
    assert declaration["nodes"][0]["tag"] == "user"
    assert declaration["nodes"][0]["content"] is None
    assert declaration["nodes"][1]["content"] == "(text | mention)*"
    assert declaration["nodes"][1]["group"] == ""
    assert list(declaration["nodes"][0]["attrs"]) == ["id", "label", "count", "enabled", "url", "image"]
    assert declaration["nodes"][0]["attrs"]["count"]["type"] == "int"
    assert declaration["nodes"][0]["attrs"]["enabled"]["type"] == "bool"
    assert declaration["nodes"][0]["attrs"]["label"]["choices"] == ["one", "two"]
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


@pytest.mark.parametrize("first, second", [
    (tm.NodeSpec("mention", kind="inline"), tm.NodeSpec("mention", kind="inline", tag="mention")),
    (tm.NodeSpec("mention", kind="inline"), tm.NodeSpec("mention", kind="inline", group="inline")),
    (tm.NodeSpec("label", kind="inline", content="text*"),
     tm.NodeSpec("label", kind="inline", content="(text)*")),
    (tm.NodeSpec("label", kind="inline", content=None), tm.NodeSpec("label", kind="inline", content="")),
    (tm.NodeSpec("mention", kind="inline", attrs={"id": tm.Attr(str), "count": tm.Attr(int)}),
     tm.NodeSpec("mention", kind="inline", attrs={"count": tm.Attr(int), "id": tm.Attr(str)})),
])
def test_node_identity_preserves_literal_declaration_fields(first, second):
    assert tm.Schema(nodes=[first]) != tm.Schema(nodes=[second])


def test_node_identity_preserves_declaration_order_and_normalizes_choices_sequences():
    first = tm.NodeSpec("first", kind="inline")
    second = tm.NodeSpec("second", kind="inline")
    assert tm.Schema(nodes=[first, second]) != tm.Schema(nodes=[second, first])
    as_tuple = tm.Schema(nodes=[tm.NodeSpec("mention", kind="inline", attrs={"id": tm.Attr(str, choices=("a",))})])
    as_list = tm.Schema(nodes=[tm.NodeSpec("mention", kind="inline", attrs={"id": tm.Attr(str, choices=["a"])})])
    assert as_tuple == as_list
    assert hash(as_tuple) == hash(as_list)


def test_node_schema_identity_is_fixed_while_declarations_remain_live():
    choices = ["red", "blue"]
    attrs = {"tone": tm.Attr(str, choices=choices)}
    nodes = (tm.NodeSpec("mention", kind="inline", attrs=attrs),)
    schema = tm.Schema(nodes=nodes)
    original = tm.Schema.from_dict(schema.to_dict())
    original_hash = hash(schema)
    cache = {schema: "cached"}

    choices.append("green")
    attrs["id"] = tm.Attr(int)

    assert schema == original
    assert hash(schema) == original_hash
    assert cache[original] == "cached"
    assert schema.nodes is nodes
    assert schema.to_dict()["nodes"][0]["attrs"]["tone"]["choices"] == choices
    assert "id" in schema.to_dict()["nodes"][0]["attrs"]
    assert schema.extend() == tm.Schema(nodes=nodes)
    assert schema.extend() != schema


def test_extend_adds_marks_and_nodes_without_changing_the_base():
    base = tm.Schema(marks=[tm.MarkSpec("underline", tag="u")], nodes=[tm.NodeSpec("mention", kind="inline")])
    before = base.to_dict()
    extended = base.extend(marks=[tm.MarkSpec("comment")],
                           nodes=[tm.NodeSpec("label", kind="inline", content="mention text*")])
    expected = tm.Schema(
        marks=[tm.MarkSpec("underline", tag="u"), tm.MarkSpec("comment")],
        nodes=[tm.NodeSpec("mention", kind="inline"), tm.NodeSpec("label", kind="inline", content="mention text*")],
    )
    assert extended == expected
    assert hash(extended) == hash(expected)
    assert base.to_dict() == before
    assert base.extend() == base
    with pytest.raises(ValueError):
        base.extend(nodes=[tm.NodeSpec("mention", kind="inline", tag="other")])
    with pytest.raises(ValueError):
        base.extend(nodes=[tm.NodeSpec("other", kind="inline", tag="U")])
    with pytest.raises(ValueError):
        base.extend(marks=[tm.MarkSpec("mention", tag="other")])


@pytest.mark.parametrize("kind", ["other", "", "INLINE"])
def test_unsupported_node_kinds_are_rejected(kind):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("custom", kind=kind)])


@pytest.mark.parametrize("node", [
    tm.NodeSpec(1, kind="inline"),
    tm.NodeSpec("mention", kind=1),
    tm.NodeSpec("mention", kind="inline", content=1),
    tm.NodeSpec("mention", kind="inline", group=1),
    tm.NodeSpec("mention", kind="inline", tag=1),
    tm.NodeSpec("mention", kind="inline", attrs=[]),
    tm.NodeSpec("mention", kind="inline", attrs={1: tm.Attr(str)}),
])
def test_wrong_node_declaration_types_are_type_errors(node):
    with pytest.raises(TypeError):
        tm.Schema(nodes=[node])


def test_nodes_must_be_an_iterable_of_node_declarations():
    with pytest.raises(TypeError):
        tm.Schema(nodes=1)


@pytest.mark.parametrize("nodes", [["mention"], [None], "mention", [tm.NodeSpec("mention", "inline", attrs={"id": str})]])
def test_node_declarations_of_the_wrong_class_fail_when_attributes_are_read(nodes):
    with pytest.raises(AttributeError):
        tm.Schema(nodes=nodes)


@pytest.mark.parametrize("name", [
    "blockquote", "bulletList", "codeBlock", "doc", "hardBreak", "heading", "horizontalRule",
    "htmlBlock", "htmlInline", "image", "listItem", "orderedList", "paragraph", "table", "tableCell",
    "tableHeader", "tableRow", "taskItem", "taskList", "text", "bold", "code", "italic", "link", "strike",
])
def test_declared_node_names_cannot_reuse_any_core_type(name):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec(name, kind="inline", tag="custom")])


@pytest.mark.parametrize("marks, nodes", [
    ([], [tm.NodeSpec("mention", "inline"), tm.NodeSpec("mention", "inline", tag="other")]),
    ([tm.MarkSpec("mention", tag="u")], [tm.NodeSpec("mention", "inline")]),
    ([], [tm.NodeSpec("first", "inline", tag="custom"), tm.NodeSpec("second", "inline", tag="custom")]),
    ([], [tm.NodeSpec("first", "inline", tag="Custom"), tm.NodeSpec("second", "inline", tag="cUSTOM")]),
    ([tm.MarkSpec("first", tag="u")], [tm.NodeSpec("second", "inline", tag="u")]),
    ([tm.MarkSpec("first", tag="Note")], [tm.NodeSpec("second", "inline", tag="nOTE")]),
])
def test_nodes_and_marks_share_type_and_tag_namespaces(marks, nodes):
    with pytest.raises(ValueError):
        tm.Schema(marks=marks, nodes=nodes)


def test_mark_exclusions_cannot_name_a_declared_node():
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("note", excludes=("mention",))], nodes=[tm.NodeSpec("mention", "inline")])


@pytest.mark.parametrize("tag", ["mention", "Mention", "custom-9", "CustomTag"])
def test_valid_node_tag_names(tag):
    assert tm.Schema(nodes=[tm.NodeSpec("mention", "inline", tag=tag)])


@pytest.mark.parametrize("tag", ["", "1u", "_u", "u_name", "u:name", "u space", "u>", "ü"])
def test_invalid_node_tag_names_are_value_errors(tag):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("mention", "inline", tag=tag)])


@pytest.mark.parametrize("tag", [
    "pre", "script", "style", "textarea", "br", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "table", "tr", "th", "td", "img", "a", "SCRIPT", "P", "Img",
])
def test_raw_text_and_core_tag_names_are_reserved_for_nodes(tag):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("mention", "inline", tag=tag)])


@pytest.mark.parametrize("name", ["_id", ":id", "data-id", "xml:lang", "a.b", "a9"])
def test_valid_node_attr_names(name):
    assert tm.Schema(nodes=[tm.NodeSpec("mention", "inline", attrs={name: tm.Attr(str)})])


@pytest.mark.parametrize("name", ["", "1id", "data id", "a/", "a>", 'a"', "é"])
def test_invalid_node_attr_names_are_value_errors(name):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("mention", "inline", attrs={name: tm.Attr(str)})])


@pytest.mark.parametrize("attr", [
    tm.Attr(str, default=1),
    tm.Attr(int, default=True),
    tm.Attr(bool, default=1),
    tm.Attr(str, choices=("red", 1)),
    tm.Attr(str, choices=("red",), default="blue"),
    tm.Attr(str, required=True, default=""),
    tm.Attr(int, uri="link"),
    tm.Attr(str, uri="other"),
    tm.Attr(str, uri="image", default=""),
])
def test_node_attrs_use_the_shared_declaration_value_rules(attr):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("mention", "inline", attrs={"value": attr})])


@pytest.mark.parametrize("content", [
    "", "mention", "symbol", "inline*", "mention emoji", "mention | emoji", "(text | mention)*",
    "text*", "text+", "mention?", "mention{0}", "mention{2}", "mention{2,}", "mention{1,3}", "mention{2,1}",
    "(mention emoji){0,2}", "  mention  emoji?  ", "text**", "(text+)?",
])
def test_content_expression_grammar_accepts_inline_names_groups_and_operators(content):
    assert tm.Schema(nodes=[
        tm.NodeSpec("wrapper", "inline", content=content),
        tm.NodeSpec("mention", "inline", group="inline symbol"),
        tm.NodeSpec("emoji", "inline"),
    ])


def test_content_expressions_resolve_forward_node_and_group_names():
    assert tm.Schema(nodes=[
        tm.NodeSpec("wrapper", "inline", content="mention symbol?"),
        tm.NodeSpec("mention", "inline", group="symbol"),
    ])


def test_explicit_groups_replace_the_kind_default_and_can_be_empty():
    assert tm.Schema(nodes=[
        tm.NodeSpec("mention", "inline", group=""),
        tm.NodeSpec("wrapper", "inline", content="mention"),
    ])
    assert tm.Schema(nodes=[
        tm.NodeSpec("mention", "inline", group="symbol marker"),
        tm.NodeSpec("wrapper", "inline", content="symbol marker?"),
    ])


@pytest.mark.parametrize("group", ["block", "inline block", "symbol block"])
def test_inline_nodes_cannot_join_the_builtin_block_group(group):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("mention", "inline", group=group)])


@pytest.mark.parametrize("content", [
    "missing", "missing*", "paragraph", "block*", "text | paragraph", "paragraph text", "inline block",
])
def test_content_expressions_reject_unknown_names_and_non_inline_content(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("wrapper", "inline", content=content)])


@pytest.mark.parametrize("content", [
    "(", "mention)", "(mention", "()", "mention |", "| mention", "mention || mention", "*mention", "mention{}",
    "mention{a}", "mention{1,2", "mention{1,2,3}", "mention{,2}", "mention @ mention",
])
def test_malformed_content_expressions_are_value_errors(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("wrapper", "inline", content=content), tm.NodeSpec("mention", "inline")])


@pytest.mark.parametrize("content", ["mention{1000000000000000000000000000}", "(mention{200}){200}"])
def test_content_expression_compilation_has_a_size_bound(content):
    with pytest.raises(ValueError):
        tm.Schema(nodes=[tm.NodeSpec("wrapper", "inline", content=content), tm.NodeSpec("mention", "inline")])


def test_serialized_nodes_use_the_same_builder_checks():
    declaration = tm.Schema(nodes=[tm.NodeSpec("mention", "inline")]).to_dict()
    declaration["nodes"].append(dict(declaration["nodes"][0]))
    with pytest.raises(ValueError):
        tm.Schema.from_dict(declaration)
    declaration = tm.Schema(nodes=[tm.NodeSpec("wrapper", "inline", content="text*")]).to_dict()
    declaration["nodes"][0]["content"] = "missing"
    with pytest.raises(ValueError):
        tm.Schema.from_dict(declaration)
    declaration = tm.Schema(nodes=[tm.NodeSpec("mention", "inline", attrs={"id": tm.Attr(int)})]).to_dict()
    declaration["nodes"][0]["attrs"]["id"]["default"] = True
    with pytest.raises(ValueError):
        tm.Schema.from_dict(declaration)


def test_node_and_node_attr_counts_have_no_schema_cap():
    many_nodes = tm.Schema(nodes=(tm.NodeSpec(f"node-{index}", "inline") for index in range(1100)))
    assert len(many_nodes.nodes) == 1100
    attrs = {f"attr-{index}": tm.Attr(str) for index in range(1100)}
    many_attrs = tm.Schema(nodes=[tm.NodeSpec("mention", "inline", attrs=attrs)])
    assert len(many_attrs.to_dict()["nodes"][0]["attrs"]) == 1100
