import copy
import json
from pathlib import Path

import pytest

import marktip as tm
from spec_examples import EDGE_DOCUMENTS, EXAMPLES, block_schema, editor_dict


def without_editor_presentation(value):
    result = copy.deepcopy(value)

    def visit(node):
        attrs = node.get("attrs", {})
        if node["type"] in ("tableCell", "tableHeader"):
            attrs.pop("colspan", None)
        if not attrs:
            node.pop("attrs", None)
        if "marks" in node:
            node["marks"].sort(key=lambda mark: json.dumps(mark, sort_keys=True))
        for child in node.get("content", []):
            visit(child)

    visit(result)
    return result


def assert_canonical_readback(document, *, schema=None, html=True):
    written = document.to_markdown()
    assert tm.from_markdown(written, schema=schema, html=html).to_markdown(canonical=True) == (
        document.to_markdown(canonical=True)
    )
    stored = json.loads(json.dumps(document.dump()))
    restored = tm.load(stored, schema=schema)
    assert restored.to_dict() == document.to_dict()
    assert restored.to_markdown() == written
    assert restored.dump() == stored


def paragraph(value):
    return {"type": "paragraph", "content": [{"type": "text", "text": value}]}


def list_block(value, *, ordered=False):
    node = {"type": "orderedList" if ordered else "bulletList", "attrs": {"tight": True},
            "content": [{"type": "listItem", "content": [paragraph(value)]}]}
    if ordered:
        node["attrs"]["start"] = 1
    return node


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("simulated", (False, True), ids=("direct", "editor"))
@pytest.mark.parametrize("markdown", EXAMPLES)
def test_spec_editor_roundtrip_keeps_source_spelling(markdown, html, simulated):
    base = tm.from_markdown(markdown, html=html)
    original = base.to_dict()
    submitted = editor_dict(original) if simulated else original
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == markdown
    assert without_editor_presentation(document.to_dict()) == without_editor_presentation(original)
    stored = json.loads(json.dumps(document.dump()))
    restored = tm.load(stored)
    assert restored.to_dict() == document.to_dict()
    assert restored.to_markdown() == markdown
    assert restored.dump() == stored


@pytest.mark.parametrize("html", (True, False))
def test_readme_editor_roundtrip_keeps_source_spelling(html):
    markdown = (Path(__file__).resolve().parents[1] / "README.md").read_bytes().decode("utf-8")
    base = tm.from_markdown(markdown, html=html)
    document = tm.from_dict(editor_dict(base.to_dict()), base=base)
    assert document.to_markdown() == markdown
    assert without_editor_presentation(document.to_dict()) == without_editor_presentation(base.to_dict())


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", EDGE_DOCUMENTS)
def test_edge_document_editor_roundtrip_keeps_source_spelling(markdown, html):
    base = tm.from_markdown(markdown, html=html)
    assert tm.from_dict(editor_dict(base.to_dict()), base=base).to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
def test_explicit_null_clears_table_alignment_and_rewrites_the_table(html):
    markdown = "| a | b |\n| :--- | ---: |\n| c | d |\n"
    base = tm.from_markdown(markdown, html=html)
    submitted = base.to_dict()
    submitted["content"][0]["content"][0]["content"][0]["attrs"]["align"] = None
    document = tm.from_dict(submitted, base=base)
    expected = tm.from_dict(submitted).to_markdown()
    assert document.to_markdown() == expected
    assert expected != markdown
    assert "align" not in document.to_dict()["content"][0]["content"][0]["content"][0].get("attrs", {})
    assert_canonical_readback(document, html=html)


MANY_BLOCKS = [
    "# Heading ###",
    "[linked][r] and *emphasis*",
    "+ first\n+ second",
    "| A | B |\n| :--- | ---: |\n| c | d |",
    "> __quoted__",
    "~~~py extra\nprint('code')\n~~~",
    "<callout tone='note'>\n*inside*\n</callout>",
]


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("action", ("edit", "delete", "move", "add"))
def test_partial_edits_preserve_every_untouched_top_level_block(html, action):
    schema = block_schema()
    markdown = "\n" + "\n\n".join(MANY_BLOCKS[:2] + ["[r]: https://example.com 'Title'"] + MANY_BLOCKS[2:]) + "\n"
    base = tm.from_markdown(markdown, schema=schema, html=html)
    submitted = base.to_dict()
    retained = list(MANY_BLOCKS)
    if action == "edit":
        submitted["content"][3]["content"][1]["content"][0]["content"][0]["content"][0]["text"] = "changed"
        retained.remove(MANY_BLOCKS[3])
    elif action == "delete":
        submitted["content"].pop(4)
        retained.remove(MANY_BLOCKS[4])
    elif action == "move":
        submitted["content"].insert(0, submitted["content"].pop(5))
    else:
        submitted["content"].insert(3, paragraph("added"))
    document = tm.from_dict(submitted, schema=schema, base=base)
    written = document.to_markdown()
    assert written.startswith("\n")
    for text in retained:
        assert text in written
    assert "[r]: https://example.com 'Title'" in written
    assert_canonical_readback(document, schema=schema, html=html)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("edited", ("container", "neighbours"))
def test_kept_and_edited_declared_containers_share_the_root_assembly(html, edited):
    schema = block_schema()
    middle = "<callout tone='info'>\n*inside*\n</callout>"
    markdown = "# Before ###\n\n" + middle + "\n\n__after__\n"
    base = tm.from_markdown(markdown, schema=schema, html=html)
    submitted = base.to_dict()
    if edited == "container":
        submitted["content"][1]["content"][0]["content"][0]["text"] = "changed"
        expected = '# Before ###\n\n<callout tone="info">\n\n*changed*\n\n</callout>\n\n__after__\n'
    else:
        submitted["content"][0]["content"][0]["text"] = "Before changed"
        submitted["content"][2]["content"][0]["text"] = "after changed"
        expected = "# Before changed\n\n" + middle + "\n\n**after changed**"
    document = tm.from_dict(submitted, schema=schema, base=base)
    assert document.to_markdown() == expected
    assert_canonical_readback(document, schema=schema, html=html)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("marker", ("-", "*", "+", ".", ")"))
@pytest.mark.parametrize("position", ("above", "below"))
def test_a_new_list_uses_a_different_marker_than_the_kept_neighbour(html, marker, position):
    ordered = marker in (".", ")")
    original = f"3{marker} *original*" if ordered else f"{marker} *original*\n{marker} second"
    base = tm.from_markdown(original + "\n", html=html)
    submitted = base.to_dict()
    submitted["content"].insert(0 if position == "above" else 1, list_block("new", ordered=ordered))
    document = tm.from_dict(submitted, base=base)
    written = document.to_markdown()
    assert original in written
    reread = tm.from_markdown(written, html=html)
    assert len(reread.to_dict()["content"]) == 2
    assert_canonical_readback(document, html=html)


@pytest.mark.parametrize("html", (True, False))
def test_a_new_bullet_list_between_two_kept_markers_remains_a_third_list(html):
    base = tm.from_markdown("- *left*\n\n* __right__\n", html=html)
    submitted = base.to_dict()
    submitted["content"].insert(1, list_block("middle"))
    document = tm.from_dict(submitted, base=base)
    written = document.to_markdown()
    assert "- *left*" in written
    assert "* __right__" in written
    assert len(tm.from_markdown(written, html=html).to_dict()["content"]) == 3
    assert_canonical_readback(document, html=html)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("left_marker, right_marker", ((".", ")"), (")", ".")))
def test_a_new_ordered_list_between_both_original_orientations_stays_separate(html, left_marker, right_marker):
    left = f"1{left_marker} __left__"
    right = f"1{right_marker} *right*"
    base = tm.from_markdown(left + "\n\n" + right + "\n", html=html)
    submitted = base.to_dict()
    submitted["content"].insert(1, list_block("middle", ordered=True))
    document = tm.from_dict(submitted, base=base)
    written = document.to_markdown()
    assert written.startswith(left + "\n\n")
    assert [node["type"] for node in tm.from_markdown(written, html=html).to_dict()["content"]] == [
        "orderedList", "orderedList", "orderedList",
    ]
    assert_canonical_readback(document, html=html)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("ordered", (False, True), ids=("bullet", "ordered"))
@pytest.mark.parametrize("action", ("delete", "empty", "move"))
def test_original_lists_that_become_neighbours_use_different_markers(html, ordered, action):
    first = "1. *first*\n2. first2" if ordered else "- *first*\n- first2"
    second = "1. __second__" if ordered else "- __second__"
    base = tm.from_markdown(first + "\n\nseparator\n\n" + second + "\n", html=html)
    submitted = base.to_dict()
    if action == "delete":
        submitted["content"].pop(1)
    elif action == "empty":
        submitted["content"][1] = {"type": "paragraph"}
    else:
        submitted["content"].insert(1, submitted["content"].pop(2))
    document = tm.from_dict(submitted, base=base)
    written = document.to_markdown()
    assert written.startswith(first + "\n\n")
    assert second not in written
    assert ("1) **second**" if ordered else "* **second**") in written
    reread = tm.from_markdown(written, html=html)
    family = "orderedList" if ordered else "bulletList"
    assert sum(child["type"] == family for child in reread.to_dict()["content"]) == 2
    assert_canonical_readback(document, html=html)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("action, expected", (
    ("keep", "# Keep ##\nbody\n"),
    ("heading", "# Changed\n\nbody\n"),
    ("paragraph", "# Keep ##\n\nchanged"),
    ("move", "body\n\n# Keep ##\n"),
    ("insert", "# Keep ##\n\nnew\n\nbody\n"),
))
def test_short_gaps_require_unchanged_original_neighbours(html, action, expected):
    base = tm.from_markdown("# Keep ##\nbody\n", html=html)
    submitted = base.to_dict()
    if action == "heading":
        submitted["content"][0]["content"][0]["text"] = "Changed"
    elif action == "paragraph":
        submitted["content"][1]["content"][0]["text"] = "changed"
    elif action == "move":
        submitted["content"].reverse()
    elif action == "insert":
        submitted["content"].insert(1, paragraph("new"))
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == expected
    assert_canonical_readback(document, html=html)


@pytest.mark.parametrize("action, expected", (
    ("keep", "# Head ###\n\nbefore\n\n[r]: /dest\n\n[link][r]\n"),
    ("delete", "# Head ###\n\n[r]: /dest\n\n[link][r]\n"),
    ("delete_earlier", "[r]: /dest\n\n[link][r]\n"),
    ("move", "# Head ###\n\n[link][r]\n\nbefore\n\n[r]: /dest\n\n"),
))
def test_source_only_definitions_follow_the_nearest_surviving_predecessor(action, expected):
    base = tm.from_markdown("# Head ###\n\nbefore\n\n[r]: /dest\n\n[link][r]\n")
    submitted = base.to_dict()
    if action == "delete":
        submitted["content"].pop(1)
    elif action == "delete_earlier":
        submitted["content"] = submitted["content"][2:]
    elif action == "move":
        submitted["content"].append(submitted["content"].pop(1))
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == expected
    assert_canonical_readback(document)


def test_equal_blocks_prefer_order_before_reusing_a_moved_block():
    base = tm.from_markdown("# Same ##\n\n# Other ###\n\nSame\n====\n")
    submitted = base.to_dict()
    submitted["content"] = [submitted["content"][1], submitted["content"][0], submitted["content"][2]]
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == "# Other ###\n\nSame\n====\n\n# Same ##\n\n"
    assert_canonical_readback(document)


@pytest.mark.parametrize("base", (None, "without_spelling"))
def test_a_base_without_spelling_lends_absent_attrs_but_no_text(base):
    markdown = "\nTitle\n=====\n\n* first\n\n* second\n"
    original = tm.from_markdown(markdown).to_dict()
    selected = tm.from_dict(original) if base is not None else None
    submitted = copy.deepcopy(original)
    submitted["content"][1]["attrs"].pop("tight")
    ordinary = tm.from_dict(submitted)
    document = tm.from_dict(submitted, base=selected)
    if selected is None:
        assert document.to_dict() == ordinary.to_dict()
        assert document.to_markdown() == ordinary.to_markdown()
    else:
        assert document.to_dict() == original
        assert document.to_dict()["content"][1]["attrs"]["tight"] is False
        assert document.to_dict() != ordinary.to_dict()
        assert document.to_markdown() == selected.to_markdown()
    assert document.to_markdown() != markdown
    assert "source" not in document.dump()


def test_base_requires_a_document():
    with pytest.raises(TypeError):
        tm.from_dict({"type": "doc", "content": []}, base={"type": "doc", "content": []})


def test_spelling_outlives_the_base_object():
    markdown = "# Keep ###\n"
    submitted = tm.from_markdown(markdown).to_dict()
    document = tm.from_dict(submitted, base=tm.from_markdown(markdown))
    assert document.to_markdown() == markdown


def test_dropped_and_free_attrs_do_not_change_spelling_but_a_carried_attr_does():
    markdown = "[x](https://old.example 'Title')\n"
    base = tm.from_markdown(markdown)
    submitted = base.to_dict()
    submitted["content"][0]["attrs"] = {"free": "value"}
    attrs = submitted["content"][0]["content"][0]["marks"][0]["attrs"]
    attrs.update(target="_blank", rel="nofollow", free="value")
    assert tm.from_dict(submitted, base=base).to_markdown() == markdown
    attrs["href"] = "https://new.example"
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == '[x](https://new.example "Title")'
    assert_canonical_readback(document)


@pytest.mark.parametrize("target", ("absent", "_self", None))
def test_matched_blocks_inherit_all_absent_attrs_and_keep_present_values(target):
    markdown = "\n[Link](https://example.com 'Title')\n\n3. _item_\n\n__tail__\n"
    parsed = tm.from_markdown(markdown)
    seeded = parsed.to_dict()
    seeded["content"][0]["content"][0]["marks"][0]["attrs"]["target"] = "_blank"
    seeded["content"][1]["attrs"]["type"] = "i"
    seeded["content"][2]["attrs"] = {"textAlign": "center"}
    base = tm.from_dict(seeded, base=parsed)
    assert base.to_markdown() == markdown

    submitted = base.to_dict()
    link_attrs = submitted["content"][0]["content"][0]["marks"][0]["attrs"]
    link_attrs.pop("target")
    submitted["content"][1]["attrs"].pop("type")
    submitted["content"][2]["attrs"].pop("textAlign")
    if target != "absent":
        link_attrs["target"] = target

    expected = base.to_dict()
    expected_link_attrs = expected["content"][0]["content"][0]["marks"][0]["attrs"]
    if target is None:
        expected_link_attrs.pop("target")
    elif target != "absent":
        expected_link_attrs["target"] = target

    document = tm.from_dict(submitted, base=base)
    assert document.to_dict() == document.dump()["doc"] == expected
    assert document.to_markdown() == markdown


@pytest.mark.parametrize("owner", ("node", "mark"))
@pytest.mark.parametrize("value, expected", (
    ("absent", "original"),
    (None, None),
    ("changed", "changed"),
))
def test_declared_attrs_distinguish_absent_null_and_changed_values(owner, value, expected):
    if owner == "node":
        schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", attrs={"label": tm.Attr(str)})])
        markdown = "<embed label='original'/>\n"
    else:
        schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"label": tm.Attr(str)})])
        markdown = "<note label='original'>*x*</note>\n"
    base = tm.from_markdown(markdown, schema=schema)
    submitted = base.to_dict()
    target = submitted["content"][0] if owner == "node" else next(
        mark for mark in submitted["content"][0]["content"][0]["marks"] if mark["type"] == "note"
    )
    if value == "absent":
        target["attrs"].pop("label")
    else:
        target["attrs"]["label"] = value
    document = tm.from_dict(submitted, schema=schema, base=base)
    restored = document.to_dict()["content"][0]
    if owner == "mark":
        restored = next(mark for mark in restored["content"][0]["marks"] if mark["type"] == "note")
    assert restored.get("attrs", {}).get("label") == expected
    if value == "absent":
        assert document.to_markdown() == markdown
    else:
        assert document.to_markdown() == tm.from_dict(submitted, schema=schema).to_markdown()


def test_reordered_marks_inherit_the_keys_of_their_type_and_occurrence():
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"id": tm.Attr(str), "label": tm.Attr(str)}, excludes=())])
    markdown = "<note id='one' label='first'><note id='two' label='second'>**x**</note></note>\n"
    base = tm.from_markdown(markdown, schema=schema)
    submitted = base.to_dict()
    marks = submitted["content"][0]["content"][0]["marks"]
    bold, first, second = marks
    second["attrs"].pop("label")
    marks[:] = [second, bold, first]

    document = tm.from_dict(submitted, schema=schema, base=base, strict="content")
    assert document.to_markdown() == markdown
    assert document.to_dict()["content"][0]["content"][0]["marks"] == [
        bold, {"type": "note", "attrs": {"id": "two", "label": "second"}}, first,
    ]


def test_inherited_tag_link_attr_reorders_marks():
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}})
    markdown = '<a href="/x" target="_self">**x**</a>'
    base = tm.from_markdown(markdown, schema=schema)
    submitted = base.to_dict()
    marks = submitted["content"][0]["content"][0]["marks"]
    marks.reverse()
    marks[0]["attrs"].pop("target")

    document = tm.from_dict(submitted, schema=schema, base=base, strict="content")
    assert document == base
    assert tm.from_markdown(document.to_markdown(canonical=True), schema=schema) == document
    assert tm.from_dict(document.to_dict(), schema=schema, strict="content") == document


def test_inherited_tag_link_attr_keeps_adjacent_code_runs_together():
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}})
    runs = [
        {"type": "text", "text": value, "marks": [
            {"type": "code"}, {"type": "link", "attrs": {"href": "/x", "target": "_self"}},
        ]}
        for value in ("a", "b")
    ]
    base = tm.from_dict({"type": "doc", "content": [{"type": "paragraph", "content": runs}]},
                        schema=schema, strict="content")
    submitted = base.to_dict()
    marks = submitted["content"][0]["content"][1]["marks"]
    marks.reverse()
    marks[0]["attrs"].pop("target")

    document = tm.from_dict(submitted, schema=schema, base=base, strict="content")
    assert document == base
    assert document.to_markdown(canonical=True) == '<a href="/x" target="_self">`ab`</a>'


def test_uri_policy_checks_input_marks_before_reordering_and_inheritance():
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"url": tm.Attr(str, uri="link")})])
    markdown = "<note url='http://example.com'>**x**</note>\n"
    base = tm.from_markdown(markdown, schema=schema)
    submitted = base.to_dict()
    marks = submitted["content"][0]["content"][0]["marks"]
    marks.reverse()
    with pytest.raises(tm.InvalidNodeError) as error:
        tm.from_dict(submitted, schema=schema, base=base, link_schemes=("https",), strict="content")
    assert error.value.code == "disallowed_scheme"
    assert error.value.path == "content[0].content[0].marks[0]"

    marks[0].pop("attrs")
    document = tm.from_dict(submitted, schema=schema, base=base, link_schemes=("https",), strict="content")
    assert document == base
    assert document.to_markdown() == markdown


def test_a_supplied_default_value_is_not_an_absent_key():
    schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", attrs={"label": tm.Attr(str, default="default")})])
    base = tm.from_markdown("<embed label='custom'/>\n", schema=schema)
    submitted = base.to_dict()
    submitted["content"][0]["attrs"]["label"] = "default"
    document = tm.from_dict(submitted, schema=schema, base=base)
    assert document.to_markdown() == "<embed/>"
    assert "label" not in document.to_dict()["content"][0].get("attrs", {})


def test_an_edited_block_does_not_inherit_an_absent_attr():
    base = tm.from_markdown("- first\n\n- second\n")
    submitted = editor_dict(base.to_dict())
    submitted["content"][0]["content"][0]["content"][0]["content"][0]["text"] = "changed"
    document = tm.from_dict(submitted, base=base)
    assert "tight" not in document.to_dict()["content"][0].get("attrs", {})
    assert document.to_markdown() == "- changed\n- second"
    assert_canonical_readback(document)


@pytest.mark.parametrize("strict", ("content", "exact"))
@pytest.mark.parametrize("owner", ("node", "mark"))
@pytest.mark.parametrize("value", ("absent", None))
def test_strict_checks_required_attrs_on_the_input_with_or_without_a_base(strict, owner, value):
    if owner == "node":
        schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", attrs={"label": tm.Attr(str, required=True)})])
        markdown = "<embed label='original'/>\n"
    else:
        schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"label": tm.Attr(str, required=True)})])
        markdown = "<note label='original'>x</note>\n"
    base = tm.from_markdown(markdown, schema=schema)
    submitted = base.to_dict()
    target = submitted["content"][0] if owner == "node" else submitted["content"][0]["content"][0]["marks"][0]
    if value == "absent":
        target["attrs"].pop("label")
        assert tm.from_dict(submitted, schema=schema, base=base).to_markdown() == markdown
    else:
        target["attrs"]["label"] = value
    with pytest.raises(tm.InvalidNodeError) as ordinary:
        tm.from_dict(submitted, schema=schema, strict=strict)
    with pytest.raises(tm.InvalidNodeError) as inherited:
        tm.from_dict(submitted, schema=schema, strict=strict, base=base)
    assert inherited.value.code == "missing_attr"
    assert type(inherited.value) is type(ordinary.value)
    assert str(inherited.value) == str(ordinary.value)
    for field in ("code", "path", "detail", "field"):
        assert getattr(inherited.value, field) == getattr(ordinary.value, field)


def test_source_spelling_is_not_borrowed_across_different_schemas():
    original_schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", tag="first")])
    changed_schema = tm.Schema(nodes=[tm.NodeSpec("embed", "block", tag="second")])
    base = tm.from_markdown("<first/>\n", schema=original_schema)
    document = tm.from_dict(base.to_dict(), schema=changed_schema, base=base)
    assert document.to_markdown() == "<second/>"


def test_empty_generated_blocks_do_not_hide_a_kept_list_neighbour():
    base = tm.from_markdown("- *kept*\n")
    submitted = base.to_dict()
    submitted["content"][:0] = [list_block("new"), {"type": "paragraph"}]
    document = tm.from_dict(submitted, base=base)
    assert document.to_markdown() == "* new\n\n- *kept*\n"
    assert_canonical_readback(document)
