"""Core schema fingerprints preserve every declaration field and its order."""

from dataclasses import replace
import json

import pytest

import marktip as tm


def fingerprint(schema):
    return tm.from_markdown("", schema=schema).dump()["schema"]


def test_default_fingerprint_known_answer():
    assert fingerprint(None) == "d4657f55662f817f"


def test_declared_fingerprint_known_answer():
    schema = tm.Schema(marks=[
        tm.MarkSpec("note", attrs={
            "label": tm.Attr(str, choices=("red", "blue"), default="red"),
            "count": tm.Attr(int, default=-2),
            "enabled": tm.Attr(bool, default=True),
            "widths": tm.Attr(tm.IntList, default=[100, 200]),
        }, excludes=("bold",)),
        tm.MarkSpec("exclusive", excludes="_"),
        tm.MarkSpec("plain"),
    ])
    assert fingerprint(schema) == "6a72285e381606f4"


@pytest.mark.parametrize("schema", (
    tm.Schema(),
    tm.Schema(
        marks=[tm.MarkSpec("note", attrs={"tone": tm.Attr(str, choices=("red", "blue"), default="red")})],
        nodes=[tm.NodeSpec("mention", "inline", attrs={"id": tm.Attr(str, required=True)})],
        core_attrs={"heading": {"textAlign": tm.Attr(str)}},
        block_image=True,
    ),
))
def test_separately_built_equal_declarations_have_the_same_fingerprint(schema):
    copied = tm.Schema.from_dict(json.loads(json.dumps(schema.to_dict())))
    assert copied is not schema
    assert copied == schema
    assert fingerprint(copied) == fingerprint(schema)


MARK = tm.MarkSpec("note")
NODE = tm.NodeSpec("custom", "inline")
IMPLICIT = tm.NodeSpec("wrapper", "block", content="block*", group="")
CARRIER = tm.NodeSpec("formula", "block", attrs={"first": tm.Attr(str), "second": tm.Attr(str)}, body="first")


@pytest.mark.parametrize("first, second", (
    pytest.param({"marks": [MARK]}, {"marks": [replace(MARK, name="other")]}, id="mark-name"),
    pytest.param({"marks": [MARK]}, {"marks": [replace(MARK, tag="note")]}, id="mark-tag"),
    pytest.param({"marks": [replace(MARK, tag="first")]},
                 {"marks": [replace(MARK, tag="second")]}, id="mark-tag-value"),
    pytest.param({"marks": [MARK]}, {"marks": [replace(MARK, attrs={"tone": tm.Attr(str)})]}, id="mark-attrs"),
    pytest.param({"marks": [MARK]}, {"marks": [replace(MARK, excludes=())]}, id="mark-excludes"),
    pytest.param({"marks": [replace(MARK, excludes="_")]},
                 {"marks": [replace(MARK, excludes=("bold",))]}, id="mark-excludes-kind"),
    pytest.param({"marks": [replace(MARK, excludes=("bold",))]},
                 {"marks": [replace(MARK, excludes=("italic",))]}, id="mark-excludes-value"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, name="other")]}, id="node-name"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, kind="block")]}, id="node-kind"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, content="inline*")]}, id="node-content"),
    pytest.param({"nodes": [replace(NODE, content="inline*")]},
                 {"nodes": [replace(NODE, content="text*")]}, id="node-content-value"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, content="")]}, id="node-content-null-empty"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, group="inline")]}, id="node-group"),
    pytest.param({"nodes": [replace(NODE, group="inline")]},
                 {"nodes": [replace(NODE, group="inline symbol")]}, id="node-group-value"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, tag="custom")]}, id="node-tag"),
    pytest.param({"nodes": [replace(NODE, tag="first")]},
                 {"nodes": [replace(NODE, tag="second")]}, id="node-tag-value"),
    pytest.param({"nodes": [NODE]}, {"nodes": [replace(NODE, attrs={"tone": tm.Attr(str)})]}, id="node-attrs"),
    pytest.param({"nodes": [IMPLICIT]}, {"nodes": [replace(IMPLICIT, implicit=True)]}, id="node-implicit"),
    pytest.param({"nodes": [CARRIER]}, {"nodes": [replace(CARRIER, fence="math")]}, id="node-fence"),
    pytest.param({"nodes": [replace(CARRIER, fence="math")]},
                 {"nodes": [replace(CARRIER, fence="equation")]}, id="node-fence-value"),
    pytest.param({"nodes": [CARRIER]}, {"nodes": [replace(CARRIER, math="display")]}, id="node-math"),
    pytest.param({"nodes": [CARRIER]}, {"nodes": [replace(CARRIER, body="second")]}, id="node-body"),
    pytest.param({"core_attrs": {"paragraph": {"tone": tm.Attr(str)}}},
                 {"core_attrs": {"heading": {"tone": tm.Attr(str)}}}, id="core-type"),
    pytest.param({"core_attrs": {"paragraph": {}}},
                 {"core_attrs": {"paragraph": {"tone": tm.Attr(str)}}}, id="core-attrs"),
    pytest.param({}, {"block_image": True}, id="block-image"),
))
def test_changing_one_declaration_field_changes_the_fingerprint(first, second):
    assert fingerprint(tm.Schema(**first)) != fingerprint(tm.Schema(**second))


def schema_with_attrs(owner, attrs):
    if owner == "mark":
        return tm.Schema(marks=[replace(MARK, attrs=attrs)])
    if owner == "node":
        return tm.Schema(nodes=[replace(NODE, attrs=attrs)])
    return tm.Schema(core_attrs={"paragraph": attrs})


@pytest.mark.parametrize("owner", ("mark", "node", "core"))
@pytest.mark.parametrize("first, second", (
    pytest.param({"value": tm.Attr(str)}, {"other": tm.Attr(str)}, id="name"),
    pytest.param({"value": tm.Attr(str)}, {"value": tm.Attr(int)}, id="type"),
    pytest.param({"value": tm.Attr(str)}, {"value": tm.Attr(str, choices=("one", "two"))}, id="choices"),
    pytest.param({"value": tm.Attr(str, choices=("one", "two"))},
                 {"value": tm.Attr(str, choices=("two", "one"))}, id="choices-order"),
    pytest.param({"value": tm.Attr(str)}, {"value": tm.Attr(str, default="one")}, id="default"),
    pytest.param({"value": tm.Attr(str, default="one")},
                 {"value": tm.Attr(str, default="two")}, id="default-value"),
    pytest.param({"value": tm.Attr(str)}, {"value": tm.Attr(str, uri="link")}, id="uri"),
    pytest.param({"value": tm.Attr(str, uri="link")},
                 {"value": tm.Attr(str, uri="image")}, id="uri-value"),
    pytest.param({"value": tm.Attr(int, default=-1)}, {"value": tm.Attr(int, default=1)}, id="integer-value"),
    pytest.param({"value": tm.Attr(bool, default=False)},
                 {"value": tm.Attr(bool, default=True)}, id="boolean-value"),
    pytest.param({"value": tm.Attr(tm.IntList, default=[100, 200])},
                 {"value": tm.Attr(tm.IntList, default=[100, 201])}, id="int-list-value"),
))
def test_changing_one_attr_field_changes_the_fingerprint(owner, first, second):
    assert fingerprint(schema_with_attrs(owner, first)) != fingerprint(schema_with_attrs(owner, second))


@pytest.mark.parametrize("owner", ("mark", "node"))
def test_attr_required_takes_part_in_the_fingerprint(owner):
    first = schema_with_attrs(owner, {"value": tm.Attr(str)})
    second = schema_with_attrs(owner, {"value": tm.Attr(str, required=True)})
    assert fingerprint(first) != fingerprint(second)


@pytest.mark.parametrize("first, second", (
    pytest.param({"marks": [MARK, tm.MarkSpec("other")]},
                 {"marks": [tm.MarkSpec("other"), MARK]}, id="marks"),
    pytest.param({"nodes": [NODE, tm.NodeSpec("other", "inline")]},
                 {"nodes": [tm.NodeSpec("other", "inline"), NODE]}, id="nodes"),
    pytest.param({"marks": [replace(MARK, attrs={"a": tm.Attr(str), "b": tm.Attr(int)})]},
                 {"marks": [replace(MARK, attrs={"b": tm.Attr(int), "a": tm.Attr(str)})]}, id="attrs"),
    pytest.param({"core_attrs": {"paragraph": {"tone": tm.Attr(str)}, "heading": {"tone": tm.Attr(str)}}},
                 {"core_attrs": {"heading": {"tone": tm.Attr(str)}, "paragraph": {"tone": tm.Attr(str)}}},
                 id="core-types"),
))
def test_declaration_order_takes_part_in_the_fingerprint(first, second):
    assert fingerprint(tm.Schema(**first)) != fingerprint(tm.Schema(**second))
