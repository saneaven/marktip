import copy
import json
from pathlib import Path
import re

import pytest

import marktip as tm


SPEC_DIR = Path(__file__).with_name("spec")
COMMONMARK = json.loads((SPEC_DIR / "commonmark-0.31.2.json").read_text(encoding="utf-8"))
GFM = re.findall(
    r"^`{32} example[^\n]*\n(.*?)^\.\n.*?^`{32}\n",
    (SPEC_DIR / "gfm-0.29.txt").read_text(encoding="utf-8"),
    re.MULTILINE | re.DOTALL,
)
_COMMONMARK_TEXTS = {example["markdown"] for example in COMMONMARK}
_GFM_MARKDOWN = [markdown.replace("→", "\t") for markdown in GFM]
EXAMPLES = [
    pytest.param(example["markdown"], id=f"commonmark-{example['example']}")
    for example in COMMONMARK
] + [
    pytest.param(markdown, id=f"gfm-{number}")
    for number, markdown in enumerate(_GFM_MARKDOWN, 1)
    if markdown not in _COMMONMARK_TEXTS
]


EDGE_DOCUMENTS = (
    "",
    "\n\n",
    " \t\r\n\t\r\n ",
    "[one]: /one\n[two]: /two\n\n",
    "\n \t\n# Title ### \t\nbody without final newline",
    "\r\n# 제목 ### \t\r\n\r\n*first*\r\n \t\r\n> 인용\r\n",
    "~~~py\ncode\n~~~ \t\n \t\n",
    "    code\n\n \t\n",
    "# Heading\n[one]: /one\n\nbody\n\n[two]: /two",
)


def block_schema(*, block_image=False):
    return tm.Schema(block_image=block_image, nodes=[
        tm.NodeSpec("callout", "block", content="block*", attrs={"tone": tm.Attr(str)}),
        tm.NodeSpec("embed", "block", attrs={"label": tm.Attr(str), "enabled": tm.Attr(bool)}),
    ])


def editor_dict(value, *, fill_empty=False, add_colspan=True):
    result = copy.deepcopy(value)

    def visit(node):
        attrs = node.get("attrs", {})
        for name in ("tight", "align", "colCount", "info"):
            attrs.pop(name, None)
        if add_colspan and node["type"] in ("tableCell", "tableHeader"):
            node.setdefault("attrs", {})["colspan"] = 1
        if fill_empty and node["type"] in ("tableCell", "tableHeader", "listItem", "taskItem"):
            if not node.get("content"):
                node["content"] = [{"type": "paragraph"}]
        node.get("marks", []).reverse()
        for child in node.get("content", []):
            visit(child)

    visit(result)
    return result
