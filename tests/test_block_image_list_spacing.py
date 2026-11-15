import pytest

import marktip as tm


@pytest.mark.parametrize("markdown", [
    "- text ![b](y.png)\n- z",
    "- ![b](y.png) text\n- z",
    "- ![a](x.png) ![b](y.png)\n- z",
    "- before ![a](x.png) after\n- z",
])
def test_markdown_block_images_do_not_loosen_lists_next_to_paragraphs_or_images(markdown):
    schema = tm.Schema(block_image=True)
    source = tm.from_markdown(markdown, schema=schema)
    assert source.to_dict()["content"][0]["attrs"]["tight"] is True
    written = source.to_markdown(canonical=True)
    assert "\n\n" not in written
    parsed = tm.from_markdown(written, schema=schema)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == written


def test_a_non_one_ordered_sublist_after_a_block_image_keeps_its_separator():
    schema = tm.Schema(block_image=True)
    source = tm.from_markdown("- ![logo](logo.png)\n\n  3. detail", schema=schema)
    children = source.to_dict()["content"][0]["content"][0]["content"]
    assert [child["type"] for child in children] == ["image", "orderedList"]
    written = source.to_markdown(canonical=True)
    assert "\n\n  3. detail" in written
    parsed = tm.from_markdown(written, schema=schema)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == written
