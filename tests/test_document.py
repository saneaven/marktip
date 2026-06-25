import pytest

import marktip as tm


def test_from_markdown_returns_document():
    doc = tm.from_markdown("# x")

    assert isinstance(doc, tm.Document)


def test_from_dict_roundtrips_and_deep_copies():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "hello", "marks": [{"type": "bold"}]},
                ],
            }
        ],
    }

    doc = tm.from_dict(ast)
    assert doc.to_dict() == ast

    ast["content"][0]["content"][0]["text"] = "changed"
    assert doc.to_dict()["content"][0]["content"][0]["text"] == "hello"


@pytest.mark.parametrize(
    "ast, message",
    [
        ({"type": "paragraph"}, "root node"),
        ({"type": "doc", "content": "bad"}, "content"),
        ({"type": "doc", "content": ["bad"]}, "content child"),
        ({"type": "doc", "attrs": "bad"}, "attrs"),
        ({"type": "doc", "marks": "bad"}, "marks"),
        ({"type": "doc", "marks": ["bad"]}, "mark"),
    ],
)
def test_from_dict_rejects_malformed_input(ast, message):
    with pytest.raises(ValueError, match=message):
        tm.from_dict(ast)


def test_old_module_level_api_is_removed():
    assert not hasattr(tm, "parse")
    assert not hasattr(tm, "to_markdown")
