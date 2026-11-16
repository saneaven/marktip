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
    with pytest.raises(tm.InvalidNodeError, match=message):
        tm.from_dict(ast)


def test_deeply_nested_markdown_raises_instead_of_crashing():
    with pytest.raises(tm.ParseError, match="maximum depth"):
        tm.from_markdown(">" * 50000 + " x")


MAX_NODE_DEPTH = 512


def test_markdown_at_the_depth_limit_reads_back_from_its_own_dict_and_dump():
    # doc, the blockquotes, list, item, paragraph, text: the text sits exactly at the limit.
    doc = tm.from_markdown(">" * (MAX_NODE_DEPTH - 4) + " - x")
    canonical = doc.to_markdown(canonical=True)

    # Compared as Markdown: `==` on dicts this deep exceeds the interpreter's recursion limit before Python 3.12.
    assert tm.from_dict(doc.to_dict()).to_markdown(canonical=True) == canonical
    assert tm.load(doc.dump()).to_markdown(canonical=True) == canonical


def test_paragraph_wrapped_around_list_item_text_counts_toward_the_depth_limit():
    with pytest.raises(tm.ParseError, match="maximum depth"):
        tm.from_markdown(">" * (MAX_NODE_DEPTH - 3) + " - x")


def test_deeply_nested_dict_raises_instead_of_crashing():
    node = {"type": "paragraph"}
    for _ in range(5000):
        node = {"type": "blockquote", "content": [node]}

    with pytest.raises(tm.InvalidNodeError, match="maximum depth"):
        tm.from_dict({"type": "doc", "content": [node]})


def test_old_module_level_api_is_removed():
    assert not hasattr(tm, "parse")
    assert not hasattr(tm, "to_markdown")
