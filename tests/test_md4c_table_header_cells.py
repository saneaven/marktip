import pytest

import marktip as tm


def block_types(markdown):
    return [node["type"] for node in tm.from_markdown(markdown).to_dict()["content"]]


def all_text(node):
    return node.get("text", "") + "".join(all_text(child) for child in node.get("content", []))


@pytest.mark.parametrize("markdown", [
    "| a | b |\n| --- |\n| 1 | 2 |",
    "| a |\n| --- | --- |\n| 1 | 2 |",
    "a | b | c\n--- | ---\n1 | 2 | 3",
])
def test_a_header_whose_cell_count_differs_from_the_delimiter_row_is_not_a_table(markdown):
    document = tm.from_markdown(markdown)

    assert block_types(markdown) == ["paragraph"]
    # Nothing the author wrote is dropped.
    assert all_text(document.to_dict()) == markdown
    assert document.to_markdown() == markdown
    assert tm.from_markdown(document.to_markdown(canonical=True)).to_dict() == document.to_dict()


def test_the_mismatched_table_stays_inside_its_container():
    document = tm.from_markdown("> | a | b |\n> | --- |\n\nafter").to_dict()

    assert [node["type"] for node in document["content"]] == ["blockquote", "paragraph"]
    assert [node["type"] for node in document["content"][0]["content"]] == ["paragraph"]


@pytest.mark.parametrize("markdown, columns", [
    ("| a | b |\n| --- | --- |\n| 1 | 2 |", 2),
    ("a | b\n--- | ---\n1 | 2", 2),
    # An escaped pipe and a pipe inside a code span do not separate cells.
    ("| a \\| b |\n| --- |\n| 1 |", 1),
    ("| `a|b` | c |\n| --- | --- |\n| 1 | 2 |", 2),
    ("| a | |\n| --- | --- |", 2),
])
def test_a_header_matching_the_delimiter_row_is_still_a_table(markdown, columns):
    table = tm.from_markdown(markdown).to_dict()["content"][0]

    assert table["type"] == "table"
    assert len(table["content"][0]["content"]) == columns


def test_a_body_row_may_still_have_more_cells_than_the_header():
    table = tm.from_markdown("| a | b |\n| --- | --- |\n| 1 | 2 | 3 |").to_dict()["content"][0]

    assert table["type"] == "table"
    assert len(table["content"][1]["content"]) == 2
