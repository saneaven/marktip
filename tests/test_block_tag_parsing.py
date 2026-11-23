"""Declared block tag lines interrupt ordinary Markdown blocks."""

import pytest

import marktip as tm


@pytest.fixture
def schema():
    return tm.Schema(nodes=[
        tm.NodeSpec("callout", "block", content="block*"),
        tm.NodeSpec("embed", "block", attrs={"id": tm.Attr(str)}),
    ])


def text(value, bold=False):
    result = {"type": "text", "text": value}
    if bold:
        result["marks"] = [{"type": "bold"}]
    return result


def paragraph(*children):
    return {"type": "paragraph", "content": list(children)}


def document(*blocks):
    return {"type": "doc", "content": list(blocks)}


def callout_blocks():
    return [{"type": "callout", "content": [paragraph(text("text "), text("bold", True))]}]


@pytest.mark.parametrize("html", [True, False])
@pytest.mark.parametrize("separator", ["\n", "\n\n"])
def test_content_between_block_tag_lines_is_ordinary_markdown(schema, html, separator):
    source = separator.join(["<callout>", "text **bold**", "</callout>"])
    assert tm.from_markdown(source, schema=schema, html=html).to_dict() == document(*callout_blocks())


@pytest.mark.parametrize("html", [True, False])
def test_closing_block_tag_is_not_absorbed_into_a_list(schema, html):
    expected = document({"type": "callout", "content": [{
        "type": "bulletList", "attrs": {"tight": True},
        "content": [{"type": "listItem", "content": [paragraph(text("item"))]}],
    }]})
    assert tm.from_markdown("<callout>\n- item\n</callout>", schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
def test_block_tag_line_interrupts_a_paragraph(schema, html):
    expected = document(paragraph(text("before")), {"type": "embed"})
    assert tm.from_markdown("before\n<embed/>", schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
def test_block_tag_line_cannot_become_a_setext_heading(schema, html):
    expected = document({"type": "embed"}, {"type": "horizontalRule"})
    assert tm.from_markdown("<embed/>\n---", schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
def test_block_tag_lines_in_a_blockquote(schema, html):
    expected = document({"type": "blockquote", "content": callout_blocks()})
    source = "> <callout>\n> text **bold**\n> </callout>"
    assert tm.from_markdown(source, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
@pytest.mark.parametrize("tight", [True, False])
def test_block_tag_lines_in_list_items(schema, html, tight):
    separator = "\n" if tight else "\n\n"
    source = separator.join(["- <callout>", "  text **bold**", "  </callout>", "- next"])
    expected = document({
        "type": "bulletList", "attrs": {"tight": tight},
        "content": [
            {"type": "listItem", "content": callout_blocks()},
            {"type": "listItem", "content": [paragraph(text("next"))]},
        ],
    })
    assert tm.from_markdown(source, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
def test_four_space_indented_block_tag_is_code(schema, html):
    expected = document({"type": "codeBlock", "content": [text("<embed/>")]})
    assert tm.from_markdown("    <embed/>", schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
def test_task_first_line_lifts_the_paragraph_carrier(schema, html):
    expected = document({
        "type": "taskList", "attrs": {"tight": True},
        "content": [{
            "type": "taskItem", "attrs": {"checked": True},
            "content": [{"type": "embed", "attrs": {"id": "u1"}}],
        }],
    })
    assert tm.from_markdown('- [x] <embed id="u1"/>', schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", [True, False])
def test_tag_directly_under_a_table_row_lifts_the_cell_paragraph_carrier(schema, html):
    expected = document({
        "type": "table", "attrs": {"colCount": 1},
        "content": [
            {"type": "tableRow", "content": [{"type": "tableHeader", "content": [paragraph(text("h"))]}]},
            {"type": "tableRow", "content": [{"type": "tableCell", "content": [{
                "type": "embed", "attrs": {"id": "u1"},
            }]}]},
        ],
    })
    source = '| h |\n| --- |\n<embed id="u1"/>'
    assert tm.from_markdown(source, schema=schema, html=html).to_dict() == expected
