import pytest

import marktip as tm


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", ("[<embed/>](https://example.com)", "**<embed/>**"))
def test_marks_around_a_lone_block_atom_are_refused(html, markdown):
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block")])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=schema, html=html)
    assert (excinfo.value.code, excinfo.value.field, excinfo.value.path) == ("invalid_mark_set", "marks", "")


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("marked", ("opening", "closing"))
def test_marks_around_a_lone_block_container_tag_are_refused(html, marked):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="block+")])
    opening = "**<callout>**" if marked == "opening" else "<callout>"
    closing = "**</callout>**" if marked == "closing" else "</callout>"
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"{opening}\n\nText\n\n{closing}", schema=schema, html=html)
    assert (excinfo.value.code, excinfo.value.field, excinfo.value.path) == ("invalid_mark_set", "marks", "")
