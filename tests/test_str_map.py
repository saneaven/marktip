"""StrMap attrs preserve ordered string maps through declarations, dicts and tags."""

import copy
import json

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
STRICT_LEVELS = ("content", "exact")
NODE_PATH = "content[0].content[0]"
PARENT_PATH = "content[0]"


def map_schema(attr=None):
    if attr is None:
        attr = tm.Attr(tm.StrMap)
    return tm.Schema(nodes=[tm.NodeSpec("measure", "inline", attrs={"data": attr})])


def doc(attrs=None):
    node = {"type": "measure"}
    if attrs:
        node["attrs"] = attrs
    return {"type": "doc", "content": [{"type": "paragraph", "content": [node]}]}


def owner_schema(owner, attrs):
    if owner == "mark":
        return tm.Schema(marks=[tm.MarkSpec("note", attrs=attrs)])
    if owner == "node":
        return tm.Schema(nodes=[tm.NodeSpec("measure", "inline", attrs=attrs)])
    return tm.Schema(core_attrs={"paragraph": attrs})


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("owner", ("mark", "inline", "block", "core-node", "core-mark"))
def test_attrs_roundtrip_on_marks_declared_nodes_and_core_types(html, owner):
    attrs = {"class": tm.Attr(str), "data": tm.Attr(tm.StrMap)}
    values = {"class": "game.status", "data": {"hp": "30", "name": "리안"}}
    spelling = 'class="game.status" data-hp="30" data-name="리안"'
    text = {"type": "text", "text": "x"}
    paragraph = {"type": "paragraph", "content": [text]}
    if owner == "mark":
        schema = tm.Schema(marks=[tm.MarkSpec("status", tag="custom-span", attrs=attrs)])
        text["marks"] = [{"type": "status", "attrs": values}]
        ast = {"type": "doc", "content": [paragraph]}
        markdown = f"<custom-span {spelling}>x</custom-span>"
    elif owner == "inline":
        schema = tm.Schema(nodes=[tm.NodeSpec("customInline", "inline", tag="custom-inline", attrs=attrs)])
        ast = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "customInline", "attrs": values},
        ]}]}
        markdown = f"<custom-inline {spelling}/>"
    elif owner == "block":
        schema = tm.Schema(nodes=[tm.NodeSpec("customDiv", "block", content="block+", tag="custom-div",
                                              attrs=attrs)])
        ast = {"type": "doc", "content": [{"type": "customDiv", "attrs": values, "content": [paragraph]}]}
        markdown = f"<custom-div {spelling}>\n\nx\n\n</custom-div>"
    elif owner == "core-node":
        schema = tm.Schema(core_attrs={"paragraph": attrs})
        paragraph["attrs"] = values
        ast = {"type": "doc", "content": [paragraph]}
        markdown = f"<p {spelling}>x</p>"
    else:
        schema = tm.Schema(core_attrs={"link": attrs})
        text["marks"] = [{"type": "link", "attrs": {"href": "/status", **values}}]
        ast = {"type": "doc", "content": [paragraph]}
        markdown = f'<a href="/status" {spelling}>x</a>'
    parsed = tm.from_markdown(markdown, schema=schema, html=html)
    assert parsed.to_dict() == ast
    assert parsed.to_markdown(canonical=True) == markdown
    for level in LEVELS:
        assert tm.from_dict(ast, schema=schema, strict=level).to_markdown(canonical=True) == markdown


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("level", LEVELS)
def test_keys_values_and_entry_order_survive_dict_and_tag_roundtrips(html, level):
    values = {"MixedCase": "", "2nd": '&"<>|`\n', "under_score:with.dot-dash": "café ' 한"}
    markdown = ('<measure data-MixedCase="" data-2nd="&amp;&quot;&lt;&gt;&#124;&#96;&#10;" '
                'data-under_score:with.dot-dash="café \' 한"/>')
    schema = map_schema()
    document = tm.from_dict(doc({"data": values}), schema=schema, strict=level)
    assert document.to_markdown(canonical=True) == markdown
    restored = tm.from_markdown(markdown, schema=schema, html=html).to_dict()
    assert restored == doc({"data": values})
    assert list(restored["content"][0]["content"][0]["attrs"]["data"]) == list(values)


@pytest.mark.parametrize("html", (True, False))
def test_maps_follow_attr_declaration_order_and_keep_their_own_tag_order(html):
    schema = tm.Schema(nodes=[tm.NodeSpec("measure", "inline", attrs={
        "before": tm.Attr(str), "aria": tm.Attr(tm.StrMap), "data": tm.Attr(tm.StrMap), "after": tm.Attr(str),
    })])
    source = '<measure data-z="z" after="a" aria-label="x" data-a="a" before="b"/>'
    parsed = tm.from_markdown(source, schema=schema, html=html)
    assert parsed.to_dict() == doc({"before": "b", "aria": {"label": "x"}, "data": {"z": "z", "a": "a"},
                                    "after": "a"})
    assert parsed.to_markdown(canonical=True) == (
        '<measure before="b" aria-label="x" data-z="z" data-a="a" after="a"/>'
    )


@pytest.mark.parametrize("spelling", ('data-hp="30"', "data-hp='30'", "data-hp=30", 'data-hp="3&#48;"'))
def test_map_values_decode_each_tag_value_form(spelling):
    assert tm.from_markdown(f"<measure {spelling} />", schema=map_schema()).to_dict() == doc({"data": {"hp": "30"}})


@pytest.mark.parametrize("level", LEVELS)
def test_map_values_use_the_same_nul_normalization_as_string_attrs(level):
    document = tm.from_dict(doc({"data": {"name": "a\0b"}}), schema=map_schema(), strict=level)
    assert document.to_dict() == doc({"data": {"name": "a\ufffdb"}})
    assert document.to_markdown(canonical=True) == '<measure data-name="a\ufffdb"/>'


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("value", (None, {}))
def test_empty_and_none_maps_are_unset(level, value):
    schema = map_schema()
    document = tm.from_dict(doc({"data": value}), schema=schema, strict=level)
    assert document.to_dict() == doc()
    assert document.to_markdown(canonical=True) == "<measure/>"
    assert tm.from_markdown("<measure/>", schema=schema).to_dict() == doc()


@pytest.mark.parametrize("value", (None, {}))
def test_unset_core_maps_leave_ordinary_markdown_form(value):
    schema = tm.Schema(core_attrs={"paragraph": {"data": tm.Attr(tm.StrMap)}})
    ast = {"type": "doc", "content": [{"type": "paragraph", "attrs": {"data": value},
                                        "content": [{"type": "text", "text": "x"}]}]}
    document = tm.from_dict(ast, schema=schema, strict="exact")
    assert "attrs" not in document.to_dict()["content"][0]
    assert document.to_markdown(canonical=True) == "x"


def test_a_nonempty_core_map_alone_selects_tag_form_from_dict():
    schema = tm.Schema(core_attrs={"paragraph": {"data": tm.Attr(tm.StrMap)}})
    ast = {"type": "doc", "content": [{"type": "paragraph", "attrs": {"data": {"hp": "30"}},
                                        "content": [{"type": "text", "text": "x"}]}]}
    document = tm.from_dict(ast, schema=schema, strict="exact")
    assert document.to_dict() == ast
    assert document.to_markdown(canonical=True) == '<p data-hp="30">x</p>'


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("value", (
    1, True, "hp=30", [], [("hp", "30")],
    {1: "30"}, {"hp": 30}, {"hp": None}, {"hp": {}},
    {"": "x"}, {"two words": "x"}, {"a/b": "x"}, {"a=b": "x"}, {"한": "x"},
))
def test_strict_maps_refuse_wrong_types_and_invalid_keys_with_the_node_location(level, value):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc({"data": value}), schema=map_schema(), strict=level)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "data"
    assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("invalid", ({1: "30"}, {"hp": 30}, {"": "x"}, {"two words": "x"}, {"a/b": "x"}))
def test_permissive_reading_discards_the_whole_invalid_map(invalid):
    values = {"valid": "kept only in a valid map", **invalid}
    assert tm.from_dict(doc({"data": values}), schema=map_schema()).to_dict() == doc()


def test_dict_values_are_stored_only_for_declared_map_attrs():
    schema = tm.Schema(nodes=[tm.NodeSpec("measure", "inline", attrs={"label": tm.Attr(str),
                                                                        "data": tm.Attr(tm.StrMap)})])
    document = tm.from_dict(doc({"unknown": {"x": "y"}, "label": {"x": "y"}, "data": {"x": "y"}}),
                            schema=schema)
    assert document.to_dict() == doc({"data": {"x": "y"}})


@pytest.mark.parametrize("spelling, code", (
    ("data-hp", "invalid_attr_value"),
    ('data-hp="30" data-hp="20"', "invalid_attr_value"),
    ('data="hp=30"', "unknown_attr"),
    ('data-="30"', "unknown_attr"),
    ('aria-label="x"', "unknown_attr"),
))
def test_bad_map_tag_attrs_report_the_expected_code(spelling, code):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"<measure {spelling}/>", schema=map_schema())
    assert excinfo.value.code == code
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_required_maps_need_at_least_one_entry(level):
    schema = map_schema(tm.Attr(tm.StrMap, required=True))
    values = {"hp": ""}
    assert tm.from_dict(doc({"data": values}), schema=schema, strict=level).to_dict() == doc({"data": values})
    for attrs in (None, {"data": None}, {"data": {}}):
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(doc(attrs), schema=schema, strict=level)
        assert excinfo.value.code == "missing_attr"
        assert excinfo.value.field == "data"
        assert excinfo.value.path == NODE_PATH
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("<measure/>", schema=schema)
    assert excinfo.value.code == "missing_attr"
    assert tm.from_markdown('<measure data-hp=""/>', schema=schema).to_dict() == doc({"data": values})


@pytest.mark.parametrize("attr", (
    tm.Attr(tm.StrMap, choices=({},)),
    tm.Attr(tm.StrMap, choices=("x",)),
    tm.Attr(tm.StrMap, default={}),
    tm.Attr(tm.StrMap, default={"hp": "30"}),
    tm.Attr(tm.StrMap, default="x"),
    tm.Attr(tm.StrMap, uri="link"),
))
def test_map_declarations_refuse_choices_default_and_uri(attr):
    with pytest.raises(ValueError):
        map_schema(attr)


@pytest.mark.parametrize("owner", ("mark", "node", "core"))
@pytest.mark.parametrize("reverse", (True, False))
@pytest.mark.parametrize("name, type_", (("data-hp", str), ("data-", str), ("data-child", tm.StrMap)))
def test_map_prefixes_cannot_overlap_other_attrs_of_the_same_owner(owner, reverse, name, type_):
    entries = [("data", tm.Attr(tm.StrMap)), (name, tm.Attr(type_))]
    if reverse:
        entries.reverse()
    with pytest.raises(ValueError):
        owner_schema(owner, dict(entries))


def test_map_prefixes_allow_unrelated_names_and_other_owners():
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"data": tm.Attr(tm.StrMap)})], nodes=[
        tm.NodeSpec("measure", "inline", attrs={"data-hp": tm.Attr(str)}),
    ], core_attrs={"paragraph": {"data": tm.Attr(tm.StrMap), "database": tm.Attr(str)}})
    assert schema.marks[0].attrs["data"].type is tm.StrMap


@pytest.mark.parametrize("inherit", (True, False))
def test_nested_marks_inherit_the_whole_map_only_when_the_inner_tag_omits_it(inherit):
    schema = tm.Schema(marks=[tm.MarkSpec("status", tag="span", attrs={
        "data": tm.Attr(tm.StrMap, inherit=inherit), "tone": tm.Attr(str),
    })])
    source = ('<span data-hp="30" data-name="리안">a<span tone="inner">b</span>'
              '<span data-hp="20" tone="inner">c</span>d</span>')
    runs = tm.from_markdown(source, schema=schema).to_dict()["content"][0]["content"]
    outer = {"hp": "30", "name": "리안"}
    assert [node["text"] for node in runs] == ["a", "b", "c", "d"]
    assert runs[0]["marks"][0]["attrs"] == {"data": outer}
    assert runs[1]["marks"][0]["attrs"] == ({"data": outer, "tone": "inner"} if inherit else {"tone": "inner"})
    assert runs[2]["marks"][0]["attrs"] == {"data": {"hp": "20"}, "tone": "inner"}
    assert runs[3]["marks"][0]["attrs"] == {"data": outer}


def test_dump_and_load_preserve_nested_objects_and_entry_order():
    schema = map_schema()
    source = "<measure data-z='last' data-a='first' />"
    original = tm.from_markdown(source, schema=schema)
    stored = json.loads(json.dumps(original.dump()))
    values = stored["doc"]["content"][0]["content"][0]["attrs"]["data"]
    assert list(values.items()) == [("z", "last"), ("a", "first")]
    loaded = tm.load(stored, schema=schema)
    assert loaded.dump() == stored
    assert loaded.to_dict() == original.to_dict()
    assert list(loaded.to_dict()["content"][0]["content"][0]["attrs"]["data"].items()) == [("z", "last"), ("a", "first")]
    assert loaded.to_markdown() == source


def test_base_preserves_source_for_equal_maps_and_changes_it_for_reordered_maps():
    schema = map_schema()
    source = "<measure data-z='last' data-a='first' />"
    base = tm.from_markdown(source, schema=schema)
    unchanged = copy.deepcopy(base.to_dict())
    assert tm.from_dict(unchanged, schema=schema, base=base).to_markdown() == source
    reordered = copy.deepcopy(unchanged)
    reordered["content"][0]["content"][0]["attrs"]["data"] = {"a": "first", "z": "last"}
    document = tm.from_dict(reordered, schema=schema, base=base)
    assert document.to_markdown() == '<measure data-a="first" data-z="last"/>'
    assert list(document.to_dict()["content"][0]["content"][0]["attrs"]["data"]) == ["a", "z"]


def test_map_order_also_distinguishes_adjacent_marks():
    schema = tm.Schema(marks=[tm.MarkSpec("status", attrs={"data": tm.Attr(tm.StrMap)})])
    source = '<status data-a="1" data-b="2">a</status><status data-b="2" data-a="1">b</status>'
    document = tm.from_markdown(source, schema=schema)
    runs = document.to_dict()["content"][0]["content"]
    assert [node["text"] for node in runs] == ["a", "b"]
    assert document.to_markdown(canonical=True) == source


@pytest.mark.parametrize("owner", ("mark", "node", "core"))
def test_schema_json_roundtrip_preserves_map_types_and_fingerprint(owner):
    schema = owner_schema(owner, {"data": tm.Attr(tm.StrMap)})
    declaration = schema.to_dict()
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    fingerprint = tm.from_markdown("", schema=schema).dump()["schema"]
    assert tm.from_markdown("", schema=restored).dump()["schema"] == fingerprint
    scalar = owner_schema(owner, {"data": tm.Attr(str)})
    assert tm.from_markdown("", schema=scalar).dump()["schema"] != fingerprint


def test_map_inherit_and_required_flags_survive_schema_roundtrip():
    schema = tm.Schema(marks=[tm.MarkSpec("status", attrs={"data": tm.Attr(tm.StrMap, required=True, inherit=True)})])
    declaration = schema.to_dict()
    assert declaration["marks"][0]["attrs"]["data"]["type"] == "StrMap"
    assert tm.Schema.from_dict(declaration) == schema


def test_map_fingerprint_known_answer():
    assert tm.from_markdown("", schema=map_schema()).dump()["schema"] == "5a947126a1a97754"
