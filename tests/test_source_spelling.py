from pathlib import Path

import pytest

import marktip as tm
from spec_examples import EXAMPLES


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", EXAMPLES)
def test_spec_markdown_keeps_its_source_spelling(markdown, html):
    document = tm.from_markdown(markdown, html=html)
    ast = document.to_dict()
    assert document.to_markdown() == markdown
    assert document.to_dict() == ast


@pytest.mark.parametrize("html", (True, False))
def test_readme_keeps_its_source_spelling(html):
    markdown = (Path(__file__).resolve().parents[1] / "README.md").read_bytes().decode("utf-8")
    assert tm.from_markdown(markdown, html=html).to_markdown() == markdown


@pytest.mark.parametrize("markdown", (
    "",
    "\n\n",
    " \t\r\n\t\r\n ",
    "[one]: /one\n[two]: /two\n\n",
    "\n \t\n# Title ### \t\nbody without final newline",
    "\r\n# 제목 ### \t\r\n\r\n*first*\r\n \t\r\n> 인용\r\n",
    "~~~py\ncode\n~~~ \t\n \t\n",
    "    code\n\n \t\n",
    "# Heading\n[one]: /one\n\nbody\n\n[two]: /two",
))
@pytest.mark.parametrize("html", (True, False))
def test_source_boundaries_keep_head_text_and_trailing_gap(markdown, html):
    assert tm.from_markdown(markdown, html=html).to_markdown() == markdown


def test_source_spelling_uses_the_existing_nul_normalization():
    markdown = "\n# a\0b\n\n```\nc\0d\n```\n"
    document = tm.from_markdown(markdown)
    assert document.to_markdown() == markdown.replace("\0", "\ufffd")
    assert document.to_dict()["content"][0]["content"][0]["text"] == "a\ufffdb"


def block_schema(*, block_image=False):
    return tm.Schema(block_image=block_image, nodes=[
        tm.NodeSpec("callout", "block", content="block*", attrs={"tone": tm.Attr(str)}),
        tm.NodeSpec("embed", "block", attrs={"label": tm.Attr(str), "enabled": tm.Attr(bool)}),
    ])


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown, types", (
    ("\n<callout tone='warning'> \t\n*body*\n</callout>\n", ["callout"]),
    ("<embed enabled='true' label='name' /> \t\n", ["embed"]),
    (
        "[outside]: /outside\n\n<callout>\n[inside]: /inside\n\n"
        "<callout tone='info'>\n# Nested ###\n</callout>\n"
        "<embed label='x'/>\n</callout>\n\n[tail]: /tail\n",
        ["callout"],
    ),
))
def test_declared_tag_line_pieces_keep_their_original_spelling(html, markdown, types):
    schema = block_schema()
    document = tm.from_markdown(markdown, schema=schema, html=html)
    ast = document.to_dict()
    assert [child["type"] for child in ast["content"]] == types
    assert document.to_markdown() == markdown
    assert tm.from_dict(ast, schema=schema).to_markdown() == document.to_markdown(canonical=True)
    assert document.to_dict() == ast


@pytest.mark.parametrize("html", (True, False))
def test_an_empty_declared_container_keeps_its_tag_lines_after_content_fill(html):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="paragraph+")])
    markdown = "<callout>\n</callout>\n"
    document = tm.from_markdown(markdown, schema=schema, html=html)
    assert document.to_dict() == {
        "type": "doc",
        "content": [{"type": "callout", "content": [{"type": "paragraph"}]}],
    }
    assert document.to_markdown() == markdown


def test_canonical_output_and_dict_content_ignore_spelling():
    markdown = "\nTitle\n=====\n\n* one\n* two\n"
    expected = {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Title"}]},
            {"type": "bulletList", "attrs": {"tight": True}, "content": [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": value}]},
                ]}
                for value in ("one", "two")
            ]},
        ],
    }
    document = tm.from_markdown(markdown)
    assert document.to_dict() == expected
    assert document.to_markdown() == markdown
    assert document.to_markdown(canonical=True) == "# Title\n\n- one\n- two"
    copied = tm.from_dict(expected)
    assert copied.to_dict() == expected
    assert copied.to_markdown() == copied.to_markdown(canonical=True) == "# Title\n\n- one\n- two"


@pytest.mark.parametrize("html", (True, False))
def test_block_image_split_rewrites_only_its_paragraph_and_keeps_surrounding_text(html):
    schema = tm.Schema(block_image=True)
    markdown = "\n# Keep ### \t\r\nleft  ![Logo](/logo.png 'A logo')  right\r\n\r\n> *untouched*\r\n"
    document = tm.from_markdown(markdown, schema=schema, html=html)
    written = document.to_markdown()
    assert written == (
        "\n# Keep ### \t\n\nleft\n\n![Logo](/logo.png \"A logo\")\n\nright\r\n\r\n> *untouched*\r\n"
    )
    assert [child["type"] for child in document.to_dict()["content"]] == [
        "heading", "paragraph", "image", "paragraph", "blockquote",
    ]
    reread = tm.from_markdown(written, schema=schema, html=html)
    assert reread.to_markdown(canonical=True) == document.to_markdown(canonical=True)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", (
    "text\n\n![Logo](/logo.png)\n",
    "text\n\n![Logo](/logo.png 'A logo')\n",
    "![a][r]\n\n[r]: /logo.png\n",
))
def test_block_image_replaced_by_one_node_keeps_its_source_spelling(markdown, html):
    document = tm.from_markdown(markdown, schema=tm.Schema(block_image=True), html=html)
    assert document.to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown, expected", (
    (
        "<callout>\n[i]: /i\n\n*in*\n</callout>\n[o]: /o\n<embed label='e'/>\n"
        "x ![c](/d.png) y\n<callout>\n__b__\n</callout>\n",
        "<callout>\n[i]: /i\n\n*in*\n</callout>\n[o]: /o\n<embed label='e'/>\n\n"
        "x\n\n![c](/d.png)\n\ny\n\n<callout>\n__b__\n</callout>\n",
    ),
    (
        "[r]: /z\n\n# Keep ##\nx ![c][r] y\n\n[q]: /q\n\n*end*\n",
        "[r]: /z\n\n# Keep ##\n\nx\n\n![c](/z)\n\ny\n\n[q]: /q\n\n*end*\n",
    ),
))
def test_generated_pieces_stay_aligned_after_merged_and_source_only_pieces(markdown, expected, html):
    document = tm.from_markdown(markdown, schema=block_schema(block_image=True), html=html)
    assert document.to_markdown() == expected


@pytest.mark.parametrize("html", (True, False))
def test_final_block_image_split_drops_its_original_trailing_gap(html):
    schema = tm.Schema(block_image=True)
    document = tm.from_markdown("left ![Logo](/logo.png) right\n", schema=schema, html=html)
    assert document.to_markdown() == "left\n\n![Logo](/logo.png)\n\nright"
    assert document.to_markdown() == document.to_markdown(canonical=True)


@pytest.mark.parametrize("html", (True, False))
def test_nested_block_image_split_keeps_the_whole_top_level_piece(html):
    schema = tm.Schema(block_image=True)
    markdown = "> before ![Logo](/logo.png) after\n"
    document = tm.from_markdown(markdown, schema=schema, html=html)
    assert [child["type"] for child in document.to_dict()["content"][0]["content"]] == [
        "paragraph", "image", "paragraph",
    ]
    assert document.to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
def test_math_postprocessing_keeps_remembered_text_around_generated_pieces(html):
    schema = tm.Schema(block_image=True, nodes=[tm.INLINE_MATH])
    markdown = "# Kept $a$ ###\n\n$x$ ![Logo](/logo.png) $y$\n\n*Kept* $z$\n"
    document = tm.from_markdown(markdown, schema=schema, html=html)
    written = document.to_markdown()
    assert written == "# Kept $a$ ###\n\n$x$\n\n![Logo](/logo.png)\n\n$y$\n\n*Kept* $z$\n"
    assert tm.from_markdown(written, schema=schema, html=html).to_markdown(canonical=True) == (
        document.to_markdown(canonical=True)
    )
