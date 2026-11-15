"""IntList attrs retain integer lists through declarations, dicts and tags."""

import json

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
STRICT_LEVELS = ("content", "exact")
NODE_PATH = "content[0].content[0]"
PARENT_PATH = "content[0]"


def list_schema(attr=None):
    if attr is None:
        attr = tm.Attr(tm.IntList)
    return tm.Schema(nodes=[tm.NodeSpec("measure", kind="inline", attrs={"sizes": attr})])


def doc(attrs=None):
    node = {"type": "measure"}
    if attrs:
        node["attrs"] = attrs
    return {"type": "doc", "content": [{"type": "paragraph", "content": [node]}]}


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("values, rendered", (([], ""), ([100], "100"), ([100, 200], "100,200"),
                                             ([-1, 0, 20], "-1,0,20")))
def test_integer_lists_are_stored_as_lists_and_written_as_comma_separated_values(level, values, rendered):
    schema = list_schema()
    ast = doc({"sizes": values})
    document = tm.from_dict(ast, schema=schema, strict=level)
    assert document.to_dict() == ast
    assert document.to_markdown(canonical=True) == f'<measure sizes="{rendered}"/>'
    assert tm.from_markdown(document.to_markdown(canonical=True), schema=schema).to_dict() == ast


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("value", (1, "100,200", True, (100, 200), [True], [1.5], ["100"], [[100]]))
def test_integer_lists_refuse_non_lists_and_non_integer_elements_with_the_node_location(level, value):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc({"sizes": value}), schema=list_schema(), strict=level)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "sizes"
    assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_required_integer_lists_accept_empty_lists_but_refuse_unset_attrs(level):
    schema = list_schema(tm.Attr(tm.IntList, required=True))
    assert tm.from_dict(doc({"sizes": []}), schema=schema, strict=level).to_dict() == doc({"sizes": []})
    for attrs in (None, {"sizes": None}):
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(doc(attrs), schema=schema, strict=level)
        assert excinfo.value.code == "missing_attr"
        assert excinfo.value.field == "sizes"
        assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("value", (None, [100, 200]))
def test_integer_list_defaults_are_unset_at_every_strict_level(level, value):
    schema = list_schema(tm.Attr(tm.IntList, default=[100, 200]))
    document = tm.from_dict(doc({"sizes": value}), schema=schema, strict=level)
    assert document.to_dict() == doc()
    assert document.to_markdown(canonical=True) == "<measure/>"
    assert tm.from_markdown('<measure sizes="100,200"/>', schema=schema).to_dict() == doc()


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_integer_list_choices_compare_the_whole_list_in_order(level):
    schema = list_schema(tm.Attr(tm.IntList, choices=([100, 200], [])))
    for values in ([100, 200], []):
        assert tm.from_dict(doc({"sizes": values}), schema=schema, strict=level).to_dict() == doc({"sizes": values})
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc({"sizes": [200, 100]}), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "sizes"
    assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("spelling", ('sizes="100,200"', "sizes='100,200'", "sizes=100,200",
                                     'sizes="100&#44;200"'))
def test_integer_lists_decode_from_each_tag_value_form(html, spelling):
    parsed = tm.from_markdown(f"<measure {spelling} />", schema=list_schema(), html=html)
    assert parsed.to_dict() == doc({"sizes": [100, 200]})


@pytest.mark.parametrize("spelling", ("sizes", 'sizes="100,,200"', 'sizes="100,wide"', 'sizes="true"'))
def test_bad_integer_list_tag_values_use_the_same_located_rule(spelling):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"<measure {spelling}/>", schema=list_schema())
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "sizes"
    assert excinfo.value.path == PARENT_PATH


def test_integer_list_tag_values_apply_choices_and_required_rules():
    schema = list_schema(tm.Attr(tm.IntList, required=True, choices=([100, 200],)))
    for markup, code in (("<measure/>", "missing_attr"), ('<measure sizes="200,100"/>', "invalid_attr_value")):
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_markdown(markup, schema=schema)
        assert excinfo.value.code == code
        assert excinfo.value.field == "sizes"
        assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("attr", (
    tm.Attr(tm.IntList, default=1),
    tm.Attr(tm.IntList, default=(100, 200)),
    tm.Attr(tm.IntList, default=[True]),
    tm.Attr(tm.IntList, choices=([100], 200)),
    tm.Attr(tm.IntList, choices=((100, 200),)),
    tm.Attr(tm.IntList, choices=([100],), default=[200]),
    tm.Attr(tm.IntList, required=True, default=[]),
    tm.Attr(tm.IntList, uri="image"),
))
def test_bad_integer_list_declaration_values_are_value_errors(attr):
    with pytest.raises(ValueError):
        list_schema(attr)


def test_integer_list_choices_and_defaults_survive_json_and_schema_hashing():
    schema = list_schema(tm.Attr(tm.IntList, choices=([], [100, 200]), default=[]))
    declaration = schema.to_dict()
    attr = declaration["nodes"][0]["attrs"]["sizes"]
    assert attr["type"] == "IntList"
    assert attr["choices"] == [[], [100, 200]]
    assert attr["default"] == []
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


def test_integer_list_identity_freezes_list_values_and_normalizes_the_outer_choices_sequence():
    values = [100, 200]
    schema = list_schema(tm.Attr(tm.IntList, choices=[values], default=values))
    original = list_schema(tm.Attr(tm.IntList, choices=([100, 200],), default=[100, 200]))
    assert schema == original
    original_hash = hash(schema)
    values.append(300)
    assert schema == original
    assert hash(schema) == original_hash
    assert schema.to_dict()["nodes"][0]["attrs"]["sizes"]["default"] == [100, 200, 300]


def test_extend_keeps_integer_list_declarations():
    base = list_schema(tm.Attr(tm.IntList, default=[]))
    before = base.to_dict()
    extended = base.extend(nodes=[tm.NodeSpec("note", kind="inline", attrs={
        "sizes": tm.Attr(tm.IntList, choices=([100], [200])),
    })])
    assert tm.Schema.from_dict(json.loads(json.dumps(extended.to_dict()))) == extended
    assert hash(tm.Schema.from_dict(extended.to_dict())) == hash(extended)
    assert base.to_dict() == before
