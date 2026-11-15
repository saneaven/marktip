"""Parsing without spelling keeps the same document and writes canonical Markdown."""

import pytest

import marktip as tm
from spec_examples import EDGE_DOCUMENTS, block_schema


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("cjk_friendly", (False, True))
@pytest.mark.parametrize("schema", (None, block_schema()), ids=("default", "declared"))
@pytest.mark.parametrize("markdown", (*EDGE_DOCUMENTS,
    "\nTitle\n=====\n\n* first\n* second\n",
    "[label][id]\n\n[id]: /target 'title'\n",
    "**볼드**은 강조 <span>x</span>\n",
))
def test_disabling_source_only_changes_spelling(markdown, schema, cjk_friendly, html):
    options = {"schema": schema, "cjk_friendly": cjk_friendly, "html": html}
    retained = tm.from_markdown(markdown, **options)
    document = tm.from_markdown(markdown, keep_source=False, **options)
    assert document.to_dict() == retained.to_dict()
    assert "source" not in document.dump()
    assert document.to_markdown() == document.to_markdown(canonical=True)
    assert document.to_markdown() == retained.to_markdown(canonical=True)
    assert document.dump() == tm.from_dict(document.to_dict(), schema=schema).dump()


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("partial", (False, True))
def test_source_can_be_disabled_for_declared_containers(html, partial):
    markdown = "<callout tone='note'>\n*body*" + ("" if partial else "\n</callout>\n")
    schema = block_schema()
    retained = tm.from_markdown(markdown, schema=schema, html=html, partial=partial)
    document = tm.from_markdown(markdown, schema=schema, html=html, partial=partial, keep_source=False)
    assert document.to_dict() == retained.to_dict()
    assert "source" not in document.dump()
    assert document.to_markdown() == document.to_markdown(canonical=True) == retained.to_markdown(canonical=True)


def test_explicit_keep_source_true_matches_the_default():
    markdown = "\nTitle\n=====\n"
    default = tm.from_markdown(markdown)
    explicit = tm.from_markdown(markdown, keep_source=True)
    assert explicit.dump() == default.dump()
    assert explicit.to_markdown() == markdown
