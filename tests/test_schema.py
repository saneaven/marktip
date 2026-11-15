"""Declarations are plain data; Schema compiles and owns their rules."""

from dataclasses import FrozenInstanceError, is_dataclass
import json

import pytest

import marktip as tm


def schema_for(attr):
    return tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": attr})])


def test_declarations_are_frozen_plain_dataclasses():
    attr = tm.Attr(str)
    mark = tm.MarkSpec("underline", tag="u")
    assert is_dataclass(attr)
    assert is_dataclass(mark)
    assert attr.type is str
    assert attr.required is False
    assert attr.choices is attr.default is attr.uri is None
    assert mark.attrs == {}
    assert mark.excludes is None
    with pytest.raises(FrozenInstanceError):
        attr.required = True
    with pytest.raises(FrozenInstanceError):
        mark.name = "other"

    # Bad declaration data is rejected when compiled, rather than by the data objects.
    invalid = tm.MarkSpec("note", attrs={"value": tm.Attr(float)})
    with pytest.raises(TypeError):
        tm.Schema(marks=[invalid])


def test_mark_declarations_have_independent_default_attr_dicts():
    first = tm.MarkSpec("first")
    second = tm.MarkSpec("second")
    assert first.attrs is not second.attrs


def test_empty_schema_equals_the_default_declaration():
    empty = tm.Schema()
    assert empty.marks == ()
    assert empty.to_dict() == {"marks": []}
    rebuilt = tm.Schema.from_dict({"marks": []})
    assert empty == rebuilt
    assert hash(empty) == hash(rebuilt)
    ast = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x"}]}]}
    assert tm.from_dict(ast, schema=empty).to_dict() == tm.from_dict(ast, schema=None).to_dict()
    assert tm.from_dict(ast, schema=empty).to_markdown(canonical=True) == tm.from_dict(ast).to_markdown(canonical=True)


@pytest.mark.parametrize("block_image", (None, 0, 1, "yes", [], {}))
def test_block_image_requires_a_bool(block_image):
    with pytest.raises(TypeError, match="block_image must be a bool"):
        tm.Schema(block_image=block_image)


def test_schema_json_roundtrip_preserves_all_declaration_fields():
    schema = tm.Schema(marks=[
        tm.MarkSpec("underline", tag="u"),
        tm.MarkSpec("comment", attrs={
            "id": tm.Attr(str, required=True),
            "tone": tm.Attr(str, choices=("red", "blue"), default="red"),
            "count": tm.Attr(int, choices=(-1, 0, 2), default=0),
            "enabled": tm.Attr(bool, choices=(False, True), default=False),
            "url": tm.Attr(str, uri="link"),
            "image": tm.Attr(str, uri="image"),
        }, excludes=()),
        tm.MarkSpec("exclusive", excludes="_"),
        tm.MarkSpec("custom", tag="Custom-9", excludes=("bold", "underline")),
    ])
    declaration = schema.to_dict()
    assert [mark["name"] for mark in declaration["marks"]] == ["underline", "comment", "exclusive", "custom"]
    assert list(declaration["marks"][1]["attrs"]) == ["id", "tone", "count", "enabled", "url", "image"]
    assert declaration["marks"][1]["attrs"]["count"]["type"] == "int"
    assert declaration["marks"][1]["attrs"]["enabled"]["type"] == "bool"
    assert declaration["marks"][1]["attrs"]["tone"]["choices"] == ["red", "blue"]
    assert declaration["marks"][1]["attrs"]["tone"]["default"] == "red"
    restored = tm.Schema.from_dict(json.loads(json.dumps(declaration)))
    assert restored == schema
    assert hash(restored) == hash(schema)
    assert restored.to_dict() == declaration
    assert {schema: "cached"}[restored] == "cached"


def test_schema_equality_preserves_declaration_and_attr_order():
    first = tm.MarkSpec("first")
    second = tm.MarkSpec("second")
    assert tm.Schema(marks=[first, second]) != tm.Schema(marks=[second, first])
    assert tm.Schema(marks=[tm.MarkSpec("note", attrs={"a": tm.Attr(str), "b": tm.Attr(int)})]) != tm.Schema(
        marks=[tm.MarkSpec("note", attrs={"b": tm.Attr(int), "a": tm.Attr(str)})]
    )
    assert tm.Schema(marks=[first]) != tm.Schema(marks=[tm.MarkSpec("first", tag="other")])
    assert tm.Schema() != object()


def test_extend_builds_a_new_schema_without_changing_the_base():
    base = tm.Schema(marks=[tm.MarkSpec("underline", tag="u")])
    before = base.to_dict()
    extended = base.extend(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str)}, excludes=("underline",))])
    expected = tm.Schema(marks=[
        tm.MarkSpec("underline", tag="u"),
        tm.MarkSpec("comment", attrs={"id": tm.Attr(str)}, excludes=("underline",)),
    ])
    assert extended == expected
    assert hash(extended) == hash(expected)
    assert base.to_dict() == before
    assert base.extend() == base
    with pytest.raises(ValueError):
        base.extend(marks=[tm.MarkSpec("underline", tag="other")])
    with pytest.raises(ValueError):
        base.extend(marks=[tm.MarkSpec("other", tag="U")])


def test_schema_accepts_forward_exclusions_and_core_mark_names():
    schema = tm.Schema(marks=[
        tm.MarkSpec("first", excludes=("second", "bold", "code", "italic", "link", "strike")),
        tm.MarkSpec("second", excludes=()),
    ])
    assert tm.Schema.from_dict(schema.to_dict()) == schema


@pytest.mark.parametrize("tag", ["u", "U", "mark-9", "CustomTag"])
def test_valid_tag_grammar(tag):
    assert tm.Schema(marks=[tm.MarkSpec("note", tag=tag)])


@pytest.mark.parametrize("name", ["_id", ":id", "data-id", "xml:lang", "a.b", "a9"])
def test_valid_attr_name_grammar(name):
    assert tm.Schema(marks=[tm.MarkSpec("note", attrs={name: tm.Attr(str)})])


@pytest.mark.parametrize("tag", ["", "1u", "_u", "u_name", "u:name", "u space", "u>", "ü"])
def test_invalid_tag_names_are_values_errors(tag):
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("note", tag=tag)])


@pytest.mark.parametrize("name", ["", "1id", "data id", "a/", "a>", 'a"', "é"])
def test_invalid_attr_names_are_value_errors(name):
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("note", attrs={name: tm.Attr(str)})])


@pytest.mark.parametrize("tag", [
    "pre", "script", "style", "textarea", "br", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "table", "tr", "th", "td", "img", "a", "SCRIPT", "P", "Img",
])
def test_raw_text_and_core_tag_names_are_reserved(tag):
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("note", tag=tag)])


@pytest.mark.parametrize("name", [
    "blockquote", "bulletList", "codeBlock", "doc", "hardBreak", "heading", "horizontalRule",
    "htmlBlock", "htmlInline", "image", "listItem", "orderedList", "paragraph", "table", "tableCell",
    "tableHeader", "tableRow", "taskItem", "taskList", "text", "bold", "code", "italic", "link", "strike",
])
def test_declared_type_names_cannot_reuse_any_core_type(name):
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec(name, tag="custom")])


@pytest.mark.parametrize("marks", [
    [tm.MarkSpec("note"), tm.MarkSpec("note", tag="other")],
    [tm.MarkSpec("first", tag="u"), tm.MarkSpec("second", tag="u")],
    [tm.MarkSpec("first", tag="Note"), tm.MarkSpec("second", tag="nOTE")],
])
def test_duplicate_names_and_case_folded_tags_are_rejected(marks):
    with pytest.raises(ValueError):
        tm.Schema(marks=marks)


@pytest.mark.parametrize("excluded", ["missing", "paragraph"])
def test_exclusions_must_name_core_or_declared_marks(excluded):
    with pytest.raises(ValueError):
        tm.Schema(marks=[tm.MarkSpec("note", excludes=(excluded,))])


@pytest.mark.parametrize("attr", [
    tm.Attr(int, uri="link"),
    tm.Attr(bool, uri="image"),
    tm.Attr(str, uri="other"),
    tm.Attr(str, uri="link", default=""),
    tm.Attr(str, uri="image", default="https://example.com/x.png"),
    tm.Attr(str, choices=("red", "blue"), default="green"),
    tm.Attr(str, required=True, default=""),
    tm.Attr(int, required=True, default=0),
    tm.Attr(bool, required=True, default=False),
    tm.Attr(int, default=10**100),
    tm.Attr(int, choices=(-10**100,)),
    tm.Attr(str, default=1),
    tm.Attr(str, default=True),
    tm.Attr(int, default=True),
    tm.Attr(bool, default=1),
    tm.Attr(str, choices=("red", 1)),
    tm.Attr(int, choices=(1, True)),
    tm.Attr(bool, choices=(True, 0)),
    tm.Attr(str, choices=(None,)),
])
def test_bad_attr_declaration_values_are_value_errors(attr):
    with pytest.raises(ValueError):
        schema_for(attr)


@pytest.mark.parametrize("attr", [
    tm.Attr(float),
    tm.Attr(list),
    tm.Attr("str"),
    tm.Attr(str, required=1),
    tm.Attr(str, uri=1),
])
def test_wrong_attr_declaration_types_are_type_errors(attr):
    with pytest.raises(TypeError):
        schema_for(attr)


@pytest.mark.parametrize("mark", [
    tm.MarkSpec(1),
    tm.MarkSpec("note", tag=1),
    tm.MarkSpec("note", attrs=[]),
    tm.MarkSpec("note", attrs={1: tm.Attr(str)}),
    tm.MarkSpec("note", excludes=(1,)),
    tm.MarkSpec("note", excludes=1),
])
def test_wrong_mark_declaration_types_are_type_errors(mark):
    with pytest.raises(TypeError):
        tm.Schema(marks=[mark])


def test_marks_must_be_an_iterable_of_mark_declarations():
    with pytest.raises(TypeError):
        tm.Schema(marks=1)


@pytest.mark.parametrize("marks", [["note"], [None], "note", [tm.MarkSpec("note", attrs={"value": str})]])
def test_declarations_of_the_wrong_class_fail_when_attributes_are_read(marks):
    with pytest.raises(AttributeError):
        tm.Schema(marks=marks)


def test_serialized_declarations_use_the_same_builder_checks():
    declaration = tm.Schema(marks=[tm.MarkSpec("note")]).to_dict()
    declaration["marks"].append(dict(declaration["marks"][0]))
    with pytest.raises(ValueError):
        tm.Schema.from_dict(declaration)
    declaration = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(int)})]).to_dict()
    declaration["marks"][0]["attrs"]["value"]["default"] = True
    with pytest.raises(ValueError):
        tm.Schema.from_dict(declaration)


def test_type_and_attr_counts_have_no_schema_cap():
    many_marks = tm.Schema(marks=(tm.MarkSpec(f"mark-{index}") for index in range(1100)))
    assert len(many_marks.to_dict()["marks"]) == 1100
    attrs = {f"attr-{index}": tm.Attr(str) for index in range(1100)}
    many_attrs = tm.Schema(marks=[tm.MarkSpec("note", attrs=attrs)])
    assert len(many_attrs.to_dict()["marks"][0]["attrs"]) == 1100


def test_schema_option_is_keyword_only_and_dict_only():
    with pytest.raises(TypeError):
        tm.from_dict({"type": "doc"}, tm.Schema())
    with pytest.raises(TypeError):
        tm.from_dict({"type": "doc"}, schema={})



def test_schema_identity_is_fixed_while_declarations_remain_live():
    choices = ["red", "blue"]
    attrs = {"tone": tm.Attr(str, choices=choices)}
    marks = (tm.MarkSpec("note", attrs=attrs),)
    schema = tm.Schema(marks=marks)
    original = tm.Schema.from_dict(schema.to_dict())
    original_hash = hash(schema)
    cache = {schema: "cached"}

    choices.append("green")
    attrs["id"] = tm.Attr(int)

    assert schema == original
    assert hash(schema) == original_hash
    assert cache[original] == "cached"
    assert schema.marks is marks
    assert schema.to_dict()["marks"][0]["attrs"]["tone"]["choices"] == choices
    assert "id" in schema.to_dict()["marks"][0]["attrs"]
    assert schema.extend() == tm.Schema(marks=marks)
    assert schema.extend() != schema
