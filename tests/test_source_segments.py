import json
from pathlib import Path
import re

import pytest

from marktip._core import _parse_segments


SPEC_DIR = Path(__file__).with_name("spec")
COMMONMARK = json.loads((SPEC_DIR / "commonmark-0.31.2.json").read_text(encoding="utf-8"))
GFM = re.findall(
    r"^`{32} example[^\n]*\n(.*?)^\.\n.*?^`{32}\n",
    (SPEC_DIR / "gfm-0.29.txt").read_text(encoding="utf-8"),
    re.MULTILINE | re.DOTALL,
)
EXAMPLES = [
    pytest.param(example["markdown"], id=f"commonmark-{example['example']}")
    for example in COMMONMARK
] + [
    pytest.param(markdown.replace("→", "\t"), id=f"gfm-{number}")
    for number, markdown in enumerate(GFM, 1)
]


def test_all_vendored_spec_examples_are_loaded():
    assert len(COMMONMARK) == 652
    assert len(GFM) == 672


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", EXAMPLES)
def test_spec_segments_match_pre_lift_root_children(markdown, html):
    result = _parse_segments(markdown, html=html)
    segments = result["segments"]
    source = markdown.encode("utf-8")
    starts = [segment["start"] for segment in segments]
    nodes = [segment["node"] for segment in segments if segment["node"] is not None]

    assert nodes == list(range(result["root_child_count"]))
    assert all(left < right for left, right in zip(starts, starts[1:]))
    line_starts = {0} | {match.end() for match in re.finditer(rb"\r\n|\r|\n", source)}
    assert all(start in line_starts and start < len(source) for start in starts)

    head = source[:starts[0]] if starts else source
    assert not head.strip(b" \t\r\n")
    for segment, extent_end in zip(segments, starts[1:] + [len(source)]):
        extent = source[segment["start"]:extent_end]
        isolated = _parse_segments(extent, html=html)
        assert isolated["root_child_count"] == int(segment["node"] is not None)


@pytest.mark.parametrize("html", (True, False))
def test_definition_only_paragraphs_remain_in_place(html):
    markdown = "\n\n# before\n\n[one]: /one\n\n> quote\n\n[two]: /two\n\nend\n"
    result = _parse_segments(markdown, html=html)
    assert result["root_child_count"] == 3
    assert [(segment["start"], segment["node"]) for segment in result["segments"]] == [
        (markdown.index("# before"), 0),
        (markdown.index("[one]:"), None),
        (markdown.index("> quote"), 1),
        (markdown.index("[two]:"), None),
        (markdown.index("end"), 2),
    ]


@pytest.mark.parametrize("container", ("> quote\n", "- item\n", "1. item\n"))
def test_definition_only_paragraph_is_removed_when_container_opens(container):
    definition = "[ref]: /url\n"
    result = _parse_segments(definition + container)
    assert result["root_child_count"] == 1
    assert [(segment["start"], segment["node"]) for segment in result["segments"]] == [
        (0, None),
        (len(definition), 0),
    ]


@pytest.mark.parametrize("markdown", ("", "\n\n", " \t\r\n\t\r\n ", "\r\r"))
def test_empty_and_blank_documents_have_no_segments(markdown):
    assert _parse_segments(markdown) == {"segments": [], "root_child_count": 0}


def test_definitions_only_document_has_a_source_only_segment():
    markdown = "\n[one]: /one\n[two]: /two\n\n"
    assert _parse_segments(markdown) == {
        "segments": [{"start": 1, "node": None}],
        "root_child_count": 0,
    }


@pytest.mark.parametrize("markdown", (
    "> [ref]: /url\n>\n> text\n",
    "- [ref]: /url\n\n  text\n",
))
def test_definitions_inside_containers_belong_to_the_container(markdown):
    result = _parse_segments(markdown)
    assert result["root_child_count"] == 1
    assert [(segment["start"], segment["node"]) for segment in result["segments"]] == [(0, 0)]


def test_setext_and_table_conversion_keep_the_original_segments():
    markdown = "Title\n=====\n\nA | B\n--- | ---\nx | y\n"
    result = _parse_segments(markdown)
    assert result["root_child_count"] == 2
    assert [(segment["start"], segment["node"]) for segment in result["segments"]] == [
        (0, 0),
        (markdown.index("A | B"), 1),
    ]


def test_setext_underline_left_after_definitions_keeps_the_same_segment():
    result = _parse_segments("[ref]: /url\n===\n")
    assert result["root_child_count"] == 1
    assert [(segment["start"], segment["node"]) for segment in result["segments"]] == [(0, 0)]


def test_offsets_count_utf8_bytes_and_preserve_physical_line_starts():
    markdown = " \t\r\n# 제목\r\n\r\n한글\r\n \t\r\n> 인용\r\n"
    source = markdown.encode("utf-8")
    result = _parse_segments(markdown)
    assert result["root_child_count"] == 3
    assert [(segment["start"], segment["node"]) for segment in result["segments"]] == [
        (source.index(b"#"), 0),
        (source.index("한글".encode("utf-8")), 1),
        (source.index(b">"), 2),
    ]
