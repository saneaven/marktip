"""Task-item continuation lines use the list marker's content column."""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value):
    return {"type": "text", "text": value}


def task_item(checked, *blocks):
    return {"type": "taskItem", "attrs": {"checked": checked}, "content": list(blocks)}


def task_list(*items, tight=True):
    return {"type": "taskList", "attrs": {"tight": tight}, "content": list(items)}


def bullet_list(value):
    return {"type": "bulletList", "attrs": {"tight": True}, "content": [
        {"type": "listItem", "content": [p(text(value))]},
    ]}


def ordered_list(start, *items):
    return {"type": "orderedList", "attrs": {"start": start, "tight": True}, "content": list(items)}


def quote(value):
    return {"type": "blockquote", "content": [p(text(value))]}


def code_block():
    return {"type": "codeBlock", "content": [text("code\n")]}


def assert_roundtrip(ast, markdown):
    source = tm.from_dict(ast)
    assert source.to_markdown() == markdown
    parsed = tm.from_markdown(markdown)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown() == markdown


def test_task_item_with_two_paragraphs_keeps_the_second_paragraph():
    ast = doc(task_list(task_item(True, p(text("first")), p(text("second"))), tight=False))
    assert_roundtrip(ast, "- [x] first\n\n  second")


@pytest.mark.parametrize("block, markdown", [
    (quote("quoted"), "- [x] first\n  > quoted"),
    (code_block(), "- [x] first\n  ```\n  code\n  ```"),
    (bullet_list("nested"), "- [x] first\n  - nested"),
])
def test_task_item_blocks_after_a_paragraph_use_the_list_marker_indent(block, markdown):
    ast = doc(task_list(task_item(True, p(text("first")), block)))
    assert_roundtrip(ast, markdown)


@pytest.mark.parametrize("checked, checkbox", [(False, " "), (True, "x")])
@pytest.mark.parametrize("block, body", [
    (quote("quoted"), "  > quoted"),
    (bullet_list("nested"), "  - nested"),
    (code_block(), "  ```\n  code\n  ```"),
    ({"type": "heading", "attrs": {"level": 2}, "content": [text("Heading")]}, "  ## Heading"),
])
def test_task_items_starting_with_a_nonparagraph_put_the_checkbox_on_its_own_line(checked, checkbox, block, body):
    ast = doc(task_list(task_item(checked, block)))
    assert_roundtrip(ast, f"- [{checkbox}]\n{body}")


def test_ordered_task_item_continuations_follow_each_number_width():
    ast = doc(ordered_list(9,
                          task_item(True, p(text("first")), bullet_list("nested one")),
                          task_item(False, p(text("second")), bullet_list("nested two"))))
    assert_roundtrip(ast, "9. [x] first\n   - nested one\n10. [ ] second\n    - nested two")


def test_ordered_task_item_starting_with_a_quote_keeps_the_checkbox_on_its_own_line():
    ast = doc(ordered_list(12, task_item(True, quote("quoted"))))
    assert_roundtrip(ast, "12. [x]\n    > quoted")


@pytest.mark.parametrize("paragraph, markdown", [
    (p(text("first\nsecond")), "- [x] first\n  second"),
    (p(text("first"), {"type": "hardBreak"}, text("second")), "- [x] first  \n  second"),
])
def test_task_item_multiline_paragraphs_keep_soft_and_hard_breaks(paragraph, markdown):
    assert_roundtrip(doc(task_list(task_item(True, paragraph))), markdown)


def test_loose_checkbox_only_line_before_a_quote_normalizes_to_an_empty_first_paragraph():
    parsed = tm.from_markdown("- [x]\n  > quoted\n\n- [ ] next")
    expected = doc(task_list(task_item(True, {"type": "paragraph"}, quote("quoted")),
                             task_item(False, p(text("next"))), tight=False))
    assert parsed.to_dict() == expected
    written = parsed.to_markdown()
    reread = tm.from_markdown(written)
    assert reread.to_dict() == expected
    assert reread.to_markdown() == written


def test_tight_checkbox_only_line_before_a_quote_does_not_add_an_empty_paragraph():
    parsed = tm.from_markdown("- [x]\n  > quoted")
    expected = doc(task_list(task_item(True, quote("quoted"))))
    assert parsed.to_dict() == expected
    written = parsed.to_markdown()
    reread = tm.from_markdown(written)
    assert reread.to_dict() == expected
    assert reread.to_markdown() == written
