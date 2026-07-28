"""from_dict schema enforcement: unknown node/mark types are rejected.

The Tiptap-side schema is closed — every extension must have a markdown mapping.
from_dict is the single enforcement point.
An unknown type raises UnknownTypeError instead of silently dropping content,
carrying structured fields (.code, .type, .path, .kind, .detail).

Grammar violations are a separate class (InvalidNodeError); both share the MarktipError base.
See test_errors.py for the hierarchy itself.
"""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def test_unknown_node_type_rejected_with_path():
    ast = doc({"type": "callout", "content": [p(text("inside"))]})
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict(ast)

    err = excinfo.value
    assert str(err) == "unknown node type 'callout' at content[0]"
    assert err.type == "callout"
    assert err.path == "content[0]"
    assert err.kind == "node"
    assert err.code == "unknown_node_type"
    assert err.detail == str(err)


def test_unknown_mark_type_rejected_with_path():
    ast = doc(p(text("x", "underline")))
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict(ast)

    err = excinfo.value
    assert str(err) == "unknown mark type 'underline' at content[0].content[0].marks[0]"
    assert err.type == "underline"
    assert err.path == "content[0].content[0].marks[0]"
    assert err.kind == "mark"
    assert err.code == "unknown_mark_type"


def test_unknown_leaf_node_rejected():
    # A leaf like a mention would previously vanish together with its label.
    ast = doc(
        p(
            text("see "),
            {"type": "mention", "attrs": {"label": "Alice"}},
            text(" now"),
        )
    )
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict(ast)

    assert excinfo.value.path == "content[0].content[1]"
    assert excinfo.value.type == "mention"


def test_unknown_type_path_points_into_deep_tree():
    ast = doc(p(text("a")), {"type": "blockquote", "content": [{"type": "widget"}]})
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict(ast)

    assert excinfo.value.path == "content[1].content[0]"


def test_unknown_mark_on_root():
    ast = {"type": "doc", "marks": [{"type": "weird"}], "content": []}
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict(ast)

    assert excinfo.value.path == "marks[0]"


def test_unknown_type_error_is_a_marktip_error():
    with pytest.raises(tm.MarktipError):
        tm.from_dict(doc({"type": "callout"}))


def test_malformed_input_is_a_distinct_class():
    # A grammar violation is not a schema violation: same base, different class,
    # so a caller can still tell "unsupported extension" from "broken document".
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict({"type": "doc", "content": "bad"})
    assert not isinstance(excinfo.value, tm.UnknownTypeError)


def test_every_known_type_accepted():
    # Whitelist-drift guard: a document using every schema type must convert.
    all_marks = ["bold", "italic", "strike", "code"]
    ast = doc(
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [text("heading"), {"type": "hardBreak"}],
        },
        p(
            text("plain"),
            text("marked", *all_marks),
            text(
                "linked",
            ),
            {
                "type": "text",
                "text": "link",
                "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
            },
            {"type": "image", "attrs": {"src": "img.png", "alt": "alt"}},
            {"type": "htmlInline", "attrs": {"html": "<u>"}},
        ),
        {"type": "blockquote", "content": [p(text("quoted"))]},
        {"type": "codeBlock", "attrs": {"language": "py"}, "content": [text("code")]},
        {"type": "horizontalRule"},
        {
            "type": "bulletList",
            "attrs": {"tight": True},
            "content": [{"type": "listItem", "content": [p(text("item"))]}],
        },
        {
            "type": "orderedList",
            "attrs": {"start": 1, "tight": True},
            "content": [{"type": "listItem", "content": [p(text("one"))]}],
        },
        {
            "type": "taskList",
            "attrs": {"tight": True},
            "content": [
                {
                    "type": "taskItem",
                    "attrs": {"checked": True},
                    "content": [p(text("done"))],
                }
            ],
        },
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableHeader", "content": [p(text("h"))]},
                        {"type": "tableCell", "content": [p(text("c"))]},
                    ],
                }
            ],
        },
        {"type": "htmlBlock", "attrs": {"html": "<div>x</div>"}},
    )
    assert tm.from_dict(ast).to_markdown()
    # Same guard on the strict side: its attr rules are a table parallel to the type
    # list, so a type added without rules fails here rather than at a caller's.
    assert tm.from_dict(ast, strict="exact").to_markdown()


def test_unknown_type_error_exported():
    assert issubclass(tm.UnknownTypeError, tm.MarktipError)
    assert "UnknownTypeError" in tm.__all__
