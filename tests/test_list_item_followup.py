import pytest

import marktip as tm


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if children:
        result["content"] = list(children)
    if attrs is not None:
        result["attrs"] = attrs
    return result


def paragraph(value):
    return node("paragraph", {"type": "text", "text": value})


def list_document(*blocks, task=False):
    item = node("taskItem" if task else "listItem", *blocks,
                attrs={"checked": True} if task else None)
    return node("doc", node("taskList" if task else "bulletList", item, attrs={"tight": True}))


def assert_roundtrip(ast, *, loose=False):
    source = tm.from_dict(ast, strict="exact")
    expected = source.to_dict()
    assert expected["content"][0]["attrs"]["tight"] is (not loose)
    written = source.to_markdown(canonical=True)
    parsed = tm.from_markdown(written)
    assert parsed.to_dict() == expected
    assert tm.from_markdown(parsed.to_markdown(canonical=True)).to_dict() == expected
    return written


@pytest.mark.parametrize("task", [False, True])
@pytest.mark.parametrize("first", [False, True])
def test_rules_inside_list_items_keep_the_rule_and_the_list_tight(task, first):
    blocks = [node("horizontalRule")] if first else [paragraph("a"), node("horizontalRule")]
    written = assert_roundtrip(list_document(*blocks, task=task))
    assert "___" in written


def test_first_rules_work_with_both_alternating_bullet_markers():
    item = node("listItem", node("horizontalRule"))
    ast = node("doc", node("bulletList", item, attrs={"tight": True}),
               node("bulletList", item, attrs={"tight": True}))
    assert assert_roundtrip(ast) == "- ___\n\n* ___"


@pytest.mark.parametrize("following, loose", [
    (tm.from_markdown("```py\nx\n```").to_dict()["content"][0], True),
    (node("heading", {"type": "text", "text": "next"}, attrs={"level": 2}), True),
    (node("bulletList", node("listItem", paragraph("next")), attrs={"tight": True}), False),
    (node("horizontalRule"), False),
    (node("blockquote", paragraph("next")), False),
    (node("orderedList", node("listItem", paragraph("next")), attrs={"start": 1, "tight": True}), False),
    (node("taskList", node("taskItem", paragraph("next"), attrs={"checked": False}),
          attrs={"tight": True}), False),
])
def test_a_block_after_a_table_stays_out_of_the_tables_rows(following, loose):
    table = tm.from_markdown("| H |\n| --- |\n| value |").to_dict()["content"][0]
    assert_roundtrip(list_document(table, following), loose=loose)


@pytest.mark.parametrize("paragraphs, tight, expected", [
    (("one",), False, True),
    (("one", "two"), True, False),
])
def test_list_tightness_is_normalized_in_tag_form(paragraphs, tight, expected):
    schema = tm.Schema(core_attrs={"bulletList": {"label": tm.Attr(str)}})
    item = node("listItem", *(paragraph(value) for value in paragraphs))
    ast = node("doc", node("bulletList", item, attrs={"tight": tight, "label": "notes"}))
    document = tm.from_dict(ast, schema=schema, strict="exact")
    written = document.to_markdown(canonical=True)
    assert written.startswith(f'<ul tight="{str(expected).lower()}" label="notes">')
    assert tm.from_markdown(written, schema=schema) == document


def test_list_tightness_is_normalized_after_inheriting_from_a_dump():
    markdown = "+ item"
    parsed = tm.from_markdown(markdown)
    stored = parsed.dump()
    stored["doc"]["content"][0]["attrs"]["tight"] = False
    base = tm.load(stored)
    submitted = base.to_dict()
    assert submitted["content"][0]["attrs"].pop("tight") is False

    document = tm.from_dict(submitted, base=base, strict="exact")
    assert document == parsed
    assert document.to_markdown() == markdown


def test_paragraph_after_a_code_fence_keeps_the_list_tight():
    ast = list_document(node("codeBlock", {"type": "text", "text": "x"}), paragraph("after"))
    assert assert_roundtrip(ast) == "- ```\n  x\n  ```\n  after"


@pytest.mark.parametrize("first", ["# h", "```\n  code\n  ```", "___"], ids=["heading", "fence", "rule"])
def test_a_table_after_a_closed_block_keeps_the_list_tight(first):
    source = f"- {first}\n  | a |\n  | - |\n  | b |\n- x"
    document = tm.from_markdown(source)
    assert document.to_dict()["content"][0]["attrs"]["tight"] is True
    written = document.to_markdown(canonical=True)
    assert written == f"- {first}\n  | a |\n  | --- |\n  | b |\n- x"
    assert tm.from_markdown(written) == document


def test_an_ordered_sublist_starting_above_one_does_not_extend_the_paragraph():
    ordered = node("orderedList", node("listItem", paragraph("x")), node("listItem", paragraph("y")),
                   attrs={"start": 3, "tight": True})
    written = assert_roundtrip(list_document(paragraph("a"), ordered), loose=True)
    assert "a\n\n  3. x" in written


