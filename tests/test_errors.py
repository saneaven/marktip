"""The exception hierarchy: every bad input raises one catchable base.

Regression cover for issue #1 — from_dict used to raise the typed UnknownTypeError
for an unknown node/mark type, but a bare ValueError for a node *structure* violation.
To a caller both mean "the input is malformed",
so a single `except MarktipError` must now catch all of them,
and each instance carries .code/.path/.detail for relaying the failure onward.
"""

import pytest

import marktip as tm

# The five inputs from the issue report, with the class/code each must produce.
ISSUE_1_CASES = [
    ({"type": "doc", "content": {"nope": 1}}, tm.InvalidNodeError, "wrong_type", ""),
    ({"type": "doc", "content": [{"content": []}]}, tm.InvalidNodeError, "missing_type", "content[0]"),
    ({"type": "paragraph"}, tm.InvalidNodeError, "invalid_root", ""),
    (
        {"type": "doc", "content": [{"type": "heading", "attrs": [], "content": []}]},
        tm.InvalidNodeError,
        "wrong_type",
        "content[0]",
    ),
    ({"type": "doc", "content": [{"type": "callout"}]}, tm.UnknownTypeError, "unknown_node_type", "content[0]"),
]


@pytest.mark.parametrize("ast", [case[0] for case in ISSUE_1_CASES])
def test_every_malformed_input_is_caught_by_the_base(ast):
    # The point of the issue: one except clause covers the lot.
    with pytest.raises(tm.MarktipError):
        tm.from_dict(ast).to_markdown()


@pytest.mark.parametrize("ast, cls, code, path", ISSUE_1_CASES)
def test_malformed_input_carries_class_code_and_path(ast, cls, code, path):
    with pytest.raises(cls) as excinfo:
        tm.from_dict(ast).to_markdown()

    err = excinfo.value
    assert err.code == code
    assert err.path == path
    assert err.detail == str(err)


def test_structure_error_points_at_the_offending_node():
    # Previously a bare ValueError with no location at all.
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(
            {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "ok"}]},
                    {"type": "blockquote", "content": [{"type": "paragraph", "content": "bad"}]},
                ],
            }
        )

    err = excinfo.value
    assert err.path == "content[1].content[0]"
    assert err.field == "content"
    assert err.code == "wrong_type"


@pytest.mark.parametrize(
    "ast, field",
    [
        ({"type": "doc", "attrs": "bad"}, "attrs"),
        ({"type": "doc", "marks": "bad"}, "marks"),
        ({"type": "doc", "content": "bad"}, "content"),
        ({"type": "doc", "content": [{"content": []}]}, "type"),
    ],
)
def test_field_names_the_offending_key(ast, field):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast)

    assert excinfo.value.field == field


def test_mark_attrs_error_keeps_the_mark_path():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "x", "marks": [{"type": "bold"}, {"type": "link", "attrs": []}]}],
            }
        ],
    }
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast)

    assert excinfo.value.path == "content[0].content[0].marks[1]"
    assert excinfo.value.field == "attrs"


def test_hierarchy():
    assert issubclass(tm.MarktipError, Exception)
    for cls in (tm.UnknownTypeError, tm.InvalidNodeError, tm.ParseError):
        assert issubclass(cls, tm.MarktipError)
        assert cls.__module__ == "marktip._core"

    # Siblings, so "unsupported extension" and "broken document" stay distinct.
    assert not issubclass(tm.InvalidNodeError, tm.UnknownTypeError)
    assert not issubclass(tm.UnknownTypeError, tm.InvalidNodeError)


def test_error_names_exported():
    for name in ("MarktipError", "UnknownTypeError", "InvalidNodeError", "ParseError"):
        assert name in tm.__all__
        assert getattr(tm, name) is not None


def test_parse_error_on_markdown_nesting():
    with pytest.raises(tm.ParseError) as excinfo:
        tm.from_markdown(">" * 50000 + " x")

    err = excinfo.value
    # The depth guard fires inside an MD4C callback, which cannot propagate a C++ exception;
    # the code must survive the round trip through the builder.
    assert err.code == "markdown_max_depth"
    assert err.path == ""
    assert err.detail == str(err)


def test_from_markdown_argument_type_is_still_a_type_error():
    # A wrong argument type is a caller bug, not a malformed document,
    # so it stays outside the hierarchy.
    with pytest.raises(TypeError) as excinfo:
        tm.from_markdown(123)

    assert not isinstance(excinfo.value, tm.MarktipError)


def test_max_depth_code_for_dict_input():
    node = {"type": "paragraph"}
    for _ in range(5000):
        node = {"type": "blockquote", "content": [node]}

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict({"type": "doc", "content": [node]})

    assert excinfo.value.code == "max_depth"
    assert excinfo.value.field == "content"


def test_unknown_mark_type_code():
    text = {"type": "text", "text": "x", "marks": [{"type": "underline"}]}
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict({"type": "doc", "content": [{"type": "paragraph", "content": [text]}]})

    assert excinfo.value.code == "unknown_mark_type"
    assert excinfo.value.kind == "mark"


def test_every_documented_code_is_reachable():
    # Guard against the README's code table drifting from what is thrown.
    # "parse_failed" is deliberately absent: it only fires on an internal MD4C failure,
    # which no input reaches from here.
    reachable = set()

    def record(fn):
        try:
            fn()
        except tm.MarktipError as e:
            reachable.add(e.code)

    deep = {"type": "paragraph"}
    for _ in range(5000):
        deep = {"type": "blockquote", "content": [deep]}

    record(lambda: tm.from_dict({"type": "doc", "content": [{"type": "callout"}]}))
    record(lambda: tm.from_dict({"type": "doc", "marks": [{"type": "underline"}], "content": []}))
    record(lambda: tm.from_dict({"type": "doc", "content": [{"content": []}]}))
    record(lambda: tm.from_dict({"type": "paragraph"}))
    record(lambda: tm.from_dict({"type": "doc", "content": "bad"}))
    record(lambda: tm.from_dict({"type": "doc", "content": [deep]}))
    record(lambda: tm.from_markdown(">" * 50000 + " x"))

    assert reachable == {
        "unknown_node_type",
        "unknown_mark_type",
        "missing_type",
        "invalid_root",
        "wrong_type",
        "max_depth",
        "markdown_max_depth",
    }
