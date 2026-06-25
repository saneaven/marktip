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


def test_roundtrip_large_and_deep_smoke():
    nested = "- root\n  - child\n    - grandchild\n"
    large = "\n".join(f"Paragraph {i} with **bold** text." for i in range(200))
    assert_stable(nested + "\n" + large)
