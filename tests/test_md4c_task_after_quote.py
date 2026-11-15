import pytest

import marktip as tm


@pytest.mark.parametrize("markdown, checked", [
    ("- [ ] a\n  > q\n- [x] b", [False, True]),
    ("- [x]\n  > quoted\n- [ ] next", [True, False]),
])
def test_a_task_item_after_a_blockquote_keeps_its_checkbox(markdown, checked):
    document = tm.from_markdown(markdown)
    items = document.to_dict()["content"][0]["content"]
    assert [item["attrs"]["checked"] for item in items] == checked
    assert items[-1]["content"][0]["content"][0]["text"] in ("b", "next")
    assert tm.from_markdown(document.to_markdown()).to_dict() == document.to_dict()
