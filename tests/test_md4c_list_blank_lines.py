import pytest

import marktip as tm


@pytest.mark.parametrize("prefix_length", (231, 232, 233))
def test_a_block_after_a_fence_stays_in_its_list_item(prefix_length):
    markdown = "x" * prefix_length + "\n\n- [ ] abc\n\n  ```py\n  a = 1\n  ```\n\n  last"
    document = tm.from_markdown(markdown)
    ast = document.to_dict()
    assert [node["type"] for node in ast["content"]] == ["paragraph", "taskList"]
    item = ast["content"][1]["content"][0]
    assert [node["type"] for node in item["content"]] == ["paragraph", "codeBlock", "paragraph"]
    assert item["content"][-1]["content"][0]["text"] == "last"
    assert tm.from_markdown(document.to_markdown()).to_dict() == ast
