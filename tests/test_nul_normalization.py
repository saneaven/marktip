"""U+0000 follows CommonMark's insecure-character normalization at both boundaries."""

import pytest

import marktip as tm


REPLACEMENT = "\ufffd"


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def assert_no_nul(value):
    if isinstance(value, str):
        assert "\0" not in value
    elif isinstance(value, dict):
        for key, item in value.items():
            assert_no_nul(key)
            assert_no_nul(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_nul(item)


def test_markdown_plain_and_inline_code_replace_nul_once():
    plain = tm.from_markdown("a\0b").to_dict()
    inline_code = tm.from_markdown("`a\0b`").to_dict()

    assert plain["content"][0]["content"][0]["text"] == f"a{REPLACEMENT}b"
    code_text = inline_code["content"][0]["content"][0]
    assert code_text["text"] == f"a{REPLACEMENT}b"
    assert code_text["marks"] == [{"type": "code"}]
    assert_no_nul(plain)
    assert_no_nul(inline_code)


@pytest.mark.parametrize("markdown", ["```\na\0b\n```", "    a\0b\n"])
def test_markdown_code_blocks_replace_nul_once_and_stay_stable(markdown):
    parsed = tm.from_markdown(markdown)
    expected = f"a{REPLACEMENT}b\n"
    assert parsed.to_dict()["content"][0]["content"][0]["text"] == expected
    assert_no_nul(parsed.to_dict())

    canonical = parsed.to_markdown()
    for _ in range(3):
        reparsed = tm.from_markdown(canonical)
        assert reparsed.to_dict()["content"][0]["content"][0]["text"] == expected
        assert reparsed.to_markdown() == canonical
        assert_no_nul(reparsed.to_dict())


@pytest.mark.parametrize("level", ["content", "exact"])
def test_markdown_html_nodes_replace_nul_and_pass_strict_roundtrip(level):
    block = tm.from_markdown('<div data-x="a\0b">c</div>\n')
    inline = tm.from_markdown('x <span data-x="a\0b">y</span> z')

    block_value = block.to_dict()
    inline_value = inline.to_dict()
    assert block_value["content"][0] == {
        "type": "htmlBlock",
        "attrs": {"html": f'<div data-x="a{REPLACEMENT}b">c</div>\n'},
    }
    assert inline_value["content"][0]["content"][1] == {
        "type": "htmlInline",
        "attrs": {"html": f'<span data-x="a{REPLACEMENT}b">'},
    }
    assert_no_nul(block_value)
    assert_no_nul(inline_value)

    block_strict = tm.from_dict(block_value, strict=level)
    inline_strict = tm.from_dict(inline_value, strict=level)
    assert block_strict.to_markdown() == block.to_markdown()
    assert inline_strict.to_markdown() == inline.to_markdown()


def test_nul_is_replaced_in_text_and_code_block_content():
    ast = doc(
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": "a\0b"}],
        },
        {
            "type": "codeBlock",
            "attrs": {"language": "py\0typed", "info": "py\0info"},
            "content": [{"type": "text", "text": "c\0d"}],
        },
    )

    converted = tm.from_dict(ast, strict="content")
    value = converted.to_dict()
    assert value["content"][0]["content"][0]["text"] == f"a{REPLACEMENT}b"
    assert value["content"][1]["attrs"] == {
        "language": f"py{REPLACEMENT}typed",
        "info": f"py{REPLACEMENT}info",
    }
    assert value["content"][1]["content"][0]["text"] == f"c{REPLACEMENT}d"

    markdown = converted.to_markdown()
    assert "\0" not in markdown
    assert tm.from_markdown(markdown).to_markdown() == markdown


def test_nul_is_replaced_in_non_uri_string_attrs():
    ast = doc(
        p(
            {
                "type": "image",
                "attrs": {
                    "src": "https://cdn.example/x.png",
                    "alt": "a\0b",
                    "title": "image\0title",
                },
            },
            {
                "type": "text",
                "text": "linked",
                "marks": [
                    {
                        "type": "link",
                        "attrs": {
                            "href": "https://example.com",
                            "title": "link\0title",
                            "target": "_\0blank",
                            "rel": "no\0opener",
                            "class": "a\0b",
                        },
                    }
                ],
            },
        ),
        {"type": "htmlBlock", "attrs": {"html": "<u>a\0b</u>"}},
    )

    value = tm.from_dict(ast, strict="content").to_dict()
    image_attrs = value["content"][0]["content"][0]["attrs"]
    link_attrs = value["content"][0]["content"][1]["marks"][0]["attrs"]
    assert image_attrs["alt"] == f"a{REPLACEMENT}b"
    assert image_attrs["title"] == f"image{REPLACEMENT}title"
    assert link_attrs["title"] == f"link{REPLACEMENT}title"
    assert link_attrs["target"] == f"_{REPLACEMENT}blank"
    assert link_attrs["rel"] == f"no{REPLACEMENT}opener"
    assert link_attrs["class"] == f"a{REPLACEMENT}b"
    assert value["content"][1]["attrs"]["html"] == f"<u>a{REPLACEMENT}b</u>"


@pytest.mark.parametrize(
    "ast, field",
    [
        (
            doc(
                p(
                    {
                        "type": "text",
                        "text": "x",
                        "marks": [{"type": "link", "attrs": {"href": "https://a\0b"}}],
                    }
                )
            ),
            "href",
        ),
        (doc(p({"type": "image", "attrs": {"src": "https://a\0b", "alt": "x"}})), "src"),
    ],
)
def test_nul_in_uri_fields_is_rejected_not_normalized(ast, field):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast)

    assert excinfo.value.code == "invalid_uri_char"
    assert excinfo.value.field == field
