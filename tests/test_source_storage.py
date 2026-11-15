import copy
import json
import re
from pathlib import Path

import pytest

import marktip as tm
from spec_examples import EDGE_DOCUMENTS, EXAMPLES, block_schema, editor_dict


def json_storage_roundtrip(document, *, schema=None):
    stored = json.loads(json.dumps(document.dump()))
    assert stored["marktip"] == 1
    assert isinstance(stored["schema"], str) and stored["schema"]
    assert stored["doc"] == document.to_dict()
    if "source" in stored:
        assert sum(item.get("node", True) for item in stored["source"]["items"]) == len(stored["doc"]["content"])
    restored = tm.load(stored, schema=schema)
    assert restored.to_dict() == document.to_dict()
    assert restored.to_markdown() == document.to_markdown()
    assert restored.dump() == stored
    return stored, restored


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", EXAMPLES)
def test_spec_dump_and_load_preserve_content_and_source(markdown, html):
    document = tm.from_markdown(markdown, html=html)
    _, restored = json_storage_roundtrip(document)
    assert restored.to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
def test_readme_dump_and_load_preserve_content_and_source(html):
    markdown = (Path(__file__).resolve().parents[1] / "README.md").read_bytes().decode("utf-8")
    _, restored = json_storage_roundtrip(tm.from_markdown(markdown, html=html))
    assert restored.to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", EDGE_DOCUMENTS)
def test_edge_document_dump_and_load_preserve_source(markdown, html):
    _, restored = json_storage_roundtrip(tm.from_markdown(markdown, html=html))
    assert restored.to_markdown() == markdown


def test_normalized_nul_source_survives_storage():
    markdown = "# a\0b\n\n```\nc\0d\n```\n"
    document = tm.from_markdown(markdown)
    _, restored = json_storage_roundtrip(document)
    assert restored.to_markdown() == markdown.replace("\0", "\ufffd")


@pytest.mark.parametrize("html", (True, False))
def test_tag_line_containers_atoms_and_internal_definitions_survive_storage(html):
    schema = block_schema()
    markdown = (
        "\n[outside]: /outside\n\n<callout tone='warning'>\n[inside]: /inside\n\n"
        "<callout>\n*text*\n</callout>\n<embed label='x'/>\n</callout>\n"
    )
    _, restored = json_storage_roundtrip(tm.from_markdown(markdown, schema=schema, html=html),
                                        schema=schema)
    assert restored.to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
def test_generated_block_image_pieces_survive_storage(html):
    schema = tm.Schema(block_image=True)
    markdown = "# Keep ###\nx ![a](/a.png) y\n\n__end__\n"
    document = tm.from_markdown(markdown, schema=schema, html=html)
    stored, _ = json_storage_roundtrip(document, schema=schema)
    items = stored["source"]["items"]
    assert ["text" in item for item in items] == [True, False, False, False, True]


def test_inherited_spelling_read_with_nondefault_options_survives_storage():
    markdown = "\n**《제목》**a <u>x</u>\n"
    base = tm.from_markdown(markdown, html=False, cjk_friendly=True)
    document = tm.from_dict(editor_dict(base.to_dict()), base=base)
    _, restored = json_storage_roundtrip(document)
    assert restored.to_markdown() == markdown


def test_an_editor_save_keeps_absent_attrs_after_load_drops_spelling():
    markdown = (
        "- first\n\n- second\n\n```python title=x\nprint('x')\n```\n\n"
        "| A | B |\n| --- | --- |\n| a | b |\n"
    )
    stored = json.loads(json.dumps(tm.from_markdown(markdown).dump()))
    schema = tm.Schema(marks=[tm.MarkSpec("extra")])
    loaded = tm.load(stored, schema=schema)
    assert "source" not in loaded.dump()
    editor_json = loaded.to_dict()
    editor_json["content"][0]["attrs"].pop("tight")
    editor_json["content"][1]["attrs"].pop("info")
    editor_json["content"][2]["attrs"].pop("colCount")
    saved = tm.from_dict(editor_json, schema=schema, base=loaded).dump()
    assert saved["doc"] == loaded.to_dict()
    assert saved["doc"]["content"][0]["attrs"]["tight"] is False
    assert saved["doc"]["content"][1]["attrs"]["info"] == "python title=x"
    assert saved["doc"]["content"][1]["attrs"]["language"] == "python"
    assert saved["doc"]["content"][2]["attrs"]["colCount"] == 2
    assert "source" not in saved


def test_equal_separately_built_schemas_keep_base_and_stored_spelling():
    original_schema = block_schema()
    equivalent_schema = tm.Schema.from_dict(json.loads(json.dumps(original_schema.to_dict())))
    assert equivalent_schema is not original_schema
    assert equivalent_schema == original_schema
    markdown = "<callout tone='warning'>\n*text*\n</callout>\n<embed label='x'/>\n"
    original = tm.from_markdown(markdown, schema=original_schema)
    inherited = tm.from_dict(original.to_dict(), schema=equivalent_schema, base=original)
    assert inherited.to_markdown() == markdown
    assert inherited.dump()["schema"] == original.dump()["schema"]
    restored = tm.load(original.dump(), schema=equivalent_schema)
    assert restored.to_dict() == original.to_dict()
    assert restored.to_markdown() == markdown


def test_the_implicit_default_schema_has_the_same_fingerprint_as_an_empty_declaration():
    markdown = "\nTitle\n=====\n"
    implicit = tm.from_markdown(markdown)
    explicit_schema = tm.Schema()
    explicit = tm.from_markdown(markdown, schema=explicit_schema)
    assert implicit.dump()["schema"] == explicit.dump()["schema"]
    assert tm.from_dict(implicit.to_dict(), schema=explicit_schema, base=implicit).to_markdown() == markdown
    assert tm.load(implicit.dump(), schema=explicit_schema).to_markdown() == markdown


@pytest.mark.parametrize("schema", (tm.Schema(), block_schema()), ids=("default", "declared"))
def test_schema_fingerprint_has_16_lowercase_hex_characters(schema):
    document = tm.from_dict({"type": "doc", "content": []}, schema=schema)
    assert re.fullmatch(r"[0-9a-f]{16}", document.dump()["schema"])


def test_a_different_schema_declaration_drops_base_and_stored_spelling():
    first_schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", tag="first")])
    second_schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", tag="second")])
    document = tm.from_markdown("<first/>\n", schema=first_schema)
    different = tm.from_markdown("<second/>\n", schema=second_schema)
    assert document.dump()["schema"] != different.dump()["schema"]
    inherited = tm.from_dict(document.to_dict(), schema=second_schema, base=document)
    restored = tm.load(document.dump(), schema=second_schema)
    assert inherited.to_markdown() == restored.to_markdown() == "<second/>"
    assert restored.to_dict() == document.to_dict()
    assert "source" not in restored.dump()


def test_a_stored_fingerprint_mismatch_drops_spelling_only():
    document = tm.from_markdown("\nTitle\n=====\n")
    stored = document.dump()
    stored["schema"] = "another declaration"
    restored = tm.load(stored)
    assert restored.to_dict() == document.to_dict()
    assert restored.to_markdown() == "# Title"
    assert "source" not in restored.dump()


@pytest.mark.parametrize("content", (
    [],
    [{"type": "paragraph"}],
    [{"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Title"}]}],
))
def test_a_document_without_spelling_omits_source_and_roundtrips(content):
    document = tm.from_dict({"type": "doc", "content": content})
    stored, restored = json_storage_roundtrip(document)
    assert "source" not in stored
    assert "source" not in restored.dump()


@pytest.mark.parametrize("version", (0, 2))
def test_load_rejects_an_unknown_storage_version(version):
    stored = tm.from_markdown("text\n").dump()
    stored["marktip"] = version
    with pytest.raises(ValueError):
        tm.load(stored)


@pytest.mark.parametrize("change", ("remove", "add"))
def test_load_drops_spelling_when_block_item_count_differs(change):
    document = tm.from_markdown("# Keep ###\n\n*body*\n")
    stored = document.dump()
    if change == "remove":
        stored["source"]["items"].pop()
    else:
        stored["source"]["items"].append({"text": "extra", "sep": ""})
    restored = tm.load(stored)
    assert restored.to_dict() == document.to_dict()
    assert restored.to_markdown() == document.to_markdown(canonical=True)
    assert "source" not in restored.dump()


def test_load_does_not_reparse_stored_text_to_check_its_content():
    document = tm.from_markdown("# Original\n")
    stored = document.dump()
    stored["source"]["items"][0]["text"] = "unrelated source"
    restored = tm.load(stored)
    assert restored.to_dict() == document.to_dict()
    assert restored.to_markdown() == "unrelated source\n"


@pytest.mark.parametrize("html", (True, False))
def test_agent_editor_storage_flow_keeps_untouched_blocks_through_two_rounds(html):
    schema = block_schema()
    kept = ("# Keep ###", "> __quote__", "<callout tone='info'>\n*inside*\n</callout>")
    markdown = "\n" + kept[0] + "\n\n*paragraph*\n\n" + kept[1] + "\n\n" + kept[2] + "\n"
    stored = json.loads(json.dumps(tm.from_markdown(markdown, schema=schema, html=html).dump()))
    for round_number in (1, 2):
        editor_json = copy.deepcopy(stored["doc"])
        editor_json["content"][1]["content"][0]["text"] = f"round {round_number}"
        base = tm.load(stored, schema=schema)
        edited = tm.from_dict(editor_json, schema=schema, base=base)
        stored = json.loads(json.dumps(edited.dump()))
        read = tm.load(stored, schema=schema)
        assert read.to_dict() == stored["doc"] == edited.to_dict()
        expected = (
            f"\n# Keep ###\n\n*round {round_number}*\n\n> __quote__\n\n"
            "<callout tone='info'>\n*inside*\n</callout>\n"
        )
        assert read.to_markdown() == edited.to_markdown() == expected
        assert read.dump() == stored
