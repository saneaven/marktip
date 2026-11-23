import copy
import json

import pytest

import marktip as tm


def paragraph(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def change_first_text(node, text="changed"):
    if node["type"] == "text":
        node["text"] = text
        return True
    for child in node.get("content", []):
        if change_first_text(child, text):
            return True
    return False


@pytest.mark.parametrize("source, declared", (
    ("+ *first*\n+ __second__\n", False),
    ("| *first* | __second__ |\n| --- | --- |\n| value | more |\n", False),
    ("> *first*\n>\n> __second__\n", False),
    ("<callout>\n*first*\n\n__second__\n</callout>\n", True),
))
def test_editing_inside_a_top_level_block_rewrites_the_whole_block(source, declared):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="block*")]) if declared else None
    base = tm.from_markdown(source, schema=schema)
    submitted = base.to_dict()
    assert change_first_text(submitted)
    document = tm.from_dict(submitted, schema=schema, base=base)
    assert document.to_markdown() == document.to_markdown(canonical=True)
    assert "__second__" not in document.to_markdown()


def test_equal_block_deletion_does_not_identify_an_original_spelling():
    base = tm.from_markdown("*same*\n\n_same_\n")
    submitted = base.to_dict()
    submitted["content"].pop(0)
    document = tm.from_dict(submitted, base=base)
    assert document.to_dict() == submitted
    assert document.to_markdown() in ("*same*\n\n", "_same_\n")


@pytest.mark.parametrize("source, expected_type", (
    ("```\ncode", "codeBlock"),
    ("<script>\nraw", "htmlBlock"),
))
def test_a_new_block_after_unclosed_source_can_be_absorbed(source, expected_type):
    base = tm.from_markdown(source)
    submitted = base.to_dict()
    submitted["content"].append(paragraph("added"))
    document = tm.from_dict(submitted, base=base)
    reread = tm.from_markdown(document.to_markdown()).to_dict()
    assert len(document.to_dict()["content"]) == 2
    assert [child["type"] for child in reread["content"]] == [expected_type]
    assert "added" in json.dumps(reread)


def test_open_declared_source_needs_partial_to_read_back_after_appending():
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="block+")])
    base = tm.from_markdown("<callout>\n\nbody", schema=schema, partial=True)
    submitted = base.to_dict()
    submitted["content"].append(paragraph("added"))
    document = tm.from_dict(submitted, schema=schema, base=base)
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(document.to_markdown(), schema=schema)
    assert excinfo.value.code == "invalid_tag"
    assert tm.from_markdown(document.to_markdown(), schema=schema, partial=True).to_dict() == {
        "type": "doc", "content": [
            {"type": "callout", "content": [paragraph("body"), paragraph("added")]},
        ],
    }
    assert tm.from_markdown(document.to_markdown(canonical=True), schema=schema).to_dict() == document.to_dict()


@pytest.mark.parametrize("action", ("move", "delete_separator"))
def test_original_indentation_after_a_list_can_be_absorbed(action):
    base = tm.from_markdown("- item\n\nseparator\n\n  paragraph\n")
    submitted = base.to_dict()
    if action == "move":
        submitted["content"].insert(1, submitted["content"].pop(2))
    else:
        submitted["content"].pop(1)
    document = tm.from_dict(submitted, base=base)
    assert "\n\n  paragraph\n" in document.to_markdown()
    reread = tm.from_markdown(document.to_markdown()).to_dict()
    first_item = reread["content"][0]["content"][0]
    assert len(first_item["content"]) == 2
    assert first_item["content"][1] == paragraph("paragraph")


def test_original_indented_code_blocks_that_become_neighbours_can_merge():
    base = tm.from_markdown("    first\n\nseparator\n\n    second\n")
    submitted = base.to_dict()
    submitted["content"].pop(1)
    document = tm.from_dict(submitted, base=base)
    assert [child["type"] for child in document.to_dict()["content"]] == ["codeBlock", "codeBlock"]
    assert document.to_markdown() == "    first\n\n    second\n"
    reread = tm.from_markdown(document.to_markdown()).to_dict()
    assert [child["type"] for child in reread["content"]] == ["codeBlock"]


@pytest.mark.parametrize("source", (
    "> [r]: /u\n>\n> inside\n\n[link][r]\n",
    "[r]: /u\ninside\n\n[link][r]\n",
    "- [r]: /u\n\n  inside\n\n[link][r]\n",
))
def test_reference_definitions_inside_an_edited_block_are_lost(source):
    base = tm.from_markdown(source)
    submitted = base.to_dict()
    assert change_first_text(submitted["content"][0])
    document = tm.from_dict(submitted, base=base)
    assert "[r]: /u" not in document.to_markdown()
    assert "[link][r]" in document.to_markdown()
    reread = tm.from_markdown(document.to_markdown()).to_dict()
    assert reread["content"][-1] == paragraph("[link][r]")
    assert document.to_dict()["content"][-1]["content"][0]["marks"][0]["type"] == "link"


def test_an_edited_loose_list_without_tight_is_written_tight():
    base = tm.from_markdown("- *first*\n\n- second\n")
    submitted = base.to_dict()
    submitted["content"][0]["attrs"].pop("tight")
    assert change_first_text(submitted["content"][0])
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == "- *changed*\n- second"
    assert tm.from_markdown(document.to_markdown()).to_dict()["content"][0]["attrs"]["tight"] is True


def test_coalescing_text_with_different_mark_order_preserves_source_spelling():
    markdown = "**_a_**_**b**_\n"
    base = tm.from_markdown(markdown)
    submitted = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "a", "marks": [{"type": "bold"}, {"type": "italic"}]},
        {"type": "text", "text": "b", "marks": [{"type": "italic"}, {"type": "bold"}]},
    ]}]}
    document = tm.from_dict(submitted, base=base)
    assert document == base
    assert document.to_markdown() == markdown


@pytest.mark.parametrize("source, expected", (
    ("![Logo](/logo.png 'Title')\n", "![Logo](/logo.png 'Title')\n"),
    ("left ![Logo](/logo.png 'Title') right\n", "left\n\n![Logo](/logo.png \"Title\")\n\nright"),
))
def test_only_real_top_level_image_splits_lose_spelling(source, expected):
    assert tm.from_markdown(source, schema=tm.Schema(block_image=True)).to_markdown() == expected


def test_dump_holds_both_content_and_remembered_markdown():
    source = "# Title ###\n"
    document = tm.from_markdown(source)
    stored = document.dump()
    assert stored["doc"] == document.to_dict()
    assert stored["source"]["items"][0]["text"] == "# Title ###"
    assert len(json.dumps(stored)) > len(json.dumps(stored["doc"]))


def test_stored_content_is_the_normalized_conversion_result():
    submitted = {"type": "doc", "unused": "ignored", "content": [
        {"type": "paragraph", "unused": "ignored", "attrs": {"unset": None, "object": {"value": "ignored"}},
         "content": [{"type": "text", "text": "body"}]},
    ]}
    document = tm.from_dict(submitted)
    expected = {"type": "doc", "content": [paragraph("body")]}
    assert document.to_dict() == expected
    assert document.dump()["doc"] == expected


def test_original_crlf_can_mix_with_new_lf_and_nul_is_normalized():
    base = tm.from_markdown("# kept ###\r\n\r\n* first\r\n* second\r\n")
    submitted = base.to_dict()
    assert change_first_text(submitted["content"][1])
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == "# kept ###\r\n\r\n- changed\n- second"
    assert tm.from_markdown("a\0b\n").to_markdown() == "a\ufffdb\n"


def test_a_base_does_not_merge_an_agent_change_into_a_stale_editor_tree():
    stale = tm.from_markdown("# Old heading\n\nbody\n").to_dict()
    agent = tm.from_markdown("# Agent heading\n\nbody\n")
    original = copy.deepcopy(stale)
    document = tm.from_dict(stale, base=agent)
    assert document.to_dict() == original
    assert "# Old heading" in document.to_markdown()
    assert "# Agent heading" not in document.to_markdown()
