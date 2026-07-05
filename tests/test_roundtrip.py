import marktip as tm


def assert_stable(markdown: str):
    doc = tm.from_markdown(markdown)
    serialized = doc.to_markdown()
    assert tm.from_markdown(serialized).to_dict() == doc.to_dict()


def test_roundtrip_core_blocks_and_marks():
    assert_stable(
        "# Title\n\n"
        "A **bold** and *italic* paragraph with `code` and ~~strike~~.\n\n"
        "> quoted\n\n"
        "- one\n"
        "- two\n\n"
        "1. first\n"
        "2. second\n"
    )


def test_roundtrip_gfm_table_task_list_and_code():
    assert_stable(
        "- [x] done\n"
        "- [ ] todo\n\n"
        "| A | B |\n"
        "| :- | -: |\n"
        "| x | y |\n\n"
        "```python\n"
        "print('ok')\n"
        "```\n"
    )


def test_roundtrip_multi_block_list_items_and_loose_lists():
    assert_stable("- first\n\n  second\n")
    assert_stable("- a\n\n- b\n")


def test_roundtrip_hard_break_inside_marks():
    assert_stable("**a\\\nb**")
    assert_stable("[a\\\nb](https://example.com)")


def test_roundtrip_block_markers_escaped_in_text():
    assert_stable("\\- not a list")
    assert_stable("\\> not a quote")
    assert_stable("1\\. not ordered")


def test_roundtrip_ordered_task_list():
    assert_stable("1. [x] done\n2. [ ] todo\n")


def test_roundtrip_large_and_deep_smoke():
    nested = "- root\n  - child\n    - grandchild\n"
    large = "\n".join(f"Paragraph {i} with **bold** text." for i in range(200))
    assert_stable(nested + "\n" + large)
