import re

import pytest

import marktip as tm
from spec_examples import COMMONMARK, EXAMPLES, GFM


def source_positions(markdown, *, html=True):
    data = tm.from_markdown(markdown, html=html).dump()
    offset = len(data["source"]["head"].encode("utf-8"))
    child = 0
    positions = []
    for item in data["source"]["items"]:
        has_node = item.get("node", True)
        positions.append((offset, child if has_node else None))
        child += int(has_node)
        offset += len((item["text"] + item["sep"]).encode("utf-8"))
    return data, positions


def test_all_vendored_spec_examples_are_loaded():
    assert len(COMMONMARK) == 652
    assert len(GFM) == 672


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", EXAMPLES)
def test_spec_source_items_match_root_children_and_partition_the_source(markdown, html):
    data, positions = source_positions(markdown, html=html)
    items = data["source"]["items"]
    source = markdown.encode("utf-8")
    starts = [start for start, _ in positions]
    nodes = [node for _, node in positions if node is not None]

    assert nodes == list(range(len(data["doc"]["content"])))
    assert all(left < right for left, right in zip(starts, starts[1:]))
    line_starts = {0} | {match.end() for match in re.finditer(rb"\r\n|\r|\n", source)}
    assert all(start in line_starts and start < len(source) for start in starts)

    head = data["source"]["head"]
    assert not head.strip(" \t\r\n")
    assert head + "".join(item["text"] + item["sep"] for item in items) == markdown
    for item in items:
        text = item["text"].encode("utf-8")
        gap = item["sep"].encode("utf-8")
        assert text
        assert not text.endswith((b"\r", b"\n"))
        assert re.split(rb"\r\n|\r|\n", text)[-1].strip(b" \t")
        assert not gap.strip(b" \t\r\n")
        assert not gap or gap.startswith((b"\r", b"\n"))
        isolated = tm.from_markdown(item["text"], html=html).to_dict()
        assert len(isolated["content"]) == int(item.get("node", True))


@pytest.mark.parametrize("html", (True, False))
def test_definition_only_paragraphs_remain_in_place(html):
    markdown = "\n\n# before\n\n[one]: /one\n\n> quote\n\n[two]: /two\n\nend\n"
    data, positions = source_positions(markdown, html=html)
    assert len(data["doc"]["content"]) == 3
    assert positions == [
        (markdown.index("# before"), 0),
        (markdown.index("[one]:"), None),
        (markdown.index("> quote"), 1),
        (markdown.index("[two]:"), None),
        (markdown.index("end"), 2),
    ]


@pytest.mark.parametrize("container", ("> quote\n", "- item\n", "1. item\n"))
def test_definition_only_paragraph_is_removed_when_container_opens(container):
    definition = "[ref]: /url\n"
    data, positions = source_positions(definition + container)
    assert len(data["doc"]["content"]) == 1
    assert positions == [(0, None), (len(definition), 0)]


@pytest.mark.parametrize("markdown", ("", "\n\n", " \t\r\n\t\r\n ", "\r\r"))
def test_empty_and_blank_documents_have_no_source_items(markdown):
    data = tm.from_markdown(markdown).dump()
    assert data["source"] == {"head": markdown, "items": []}
    assert data["doc"] == {"type": "doc", "content": []}


def test_definitions_only_document_has_a_source_only_item():
    markdown = "\n[one]: /one\n[two]: /two\n\n"
    data = tm.from_markdown(markdown).dump()
    assert data["source"] == {
        "head": "\n",
        "items": [{"text": "[one]: /one\n[two]: /two", "sep": "\n\n", "node": False}],
    }
    assert data["doc"]["content"] == []


@pytest.mark.parametrize("markdown", (
    "> [ref]: /url\n>\n> text\n",
    "- [ref]: /url\n\n  text\n",
))
def test_definitions_inside_containers_belong_to_the_container(markdown):
    data, positions = source_positions(markdown)
    assert len(data["doc"]["content"]) == 1
    assert positions == [(0, 0)]


def test_setext_and_table_conversion_keep_the_original_items():
    markdown = "Title\n=====\n\nA | B\n--- | ---\nx | y\n"
    data, positions = source_positions(markdown)
    assert len(data["doc"]["content"]) == 2
    assert positions == [(0, 0), (markdown.index("A | B"), 1)]


def test_setext_underline_left_after_definitions_keeps_the_same_item():
    data, positions = source_positions("[ref]: /url\n===\n")
    assert len(data["doc"]["content"]) == 1
    assert positions == [(0, 0)]


def test_source_positions_count_utf8_bytes_and_preserve_physical_line_starts():
    markdown = " \t\r\n# 제목\r\n\r\n한글\r\n \t\r\n> 인용\r\n"
    source = markdown.encode("utf-8")
    data, positions = source_positions(markdown)
    assert len(data["doc"]["content"]) == 3
    assert positions == [
        (source.index(b"#"), 0),
        (source.index("한글".encode("utf-8")), 1),
        (source.index(b">"), 2),
    ]
