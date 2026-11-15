import json
from pathlib import Path
import re

import pytest


SPEC_DIR = Path(__file__).with_name("spec")
COMMONMARK = json.loads((SPEC_DIR / "commonmark-0.31.2.json").read_text(encoding="utf-8"))
GFM = re.findall(
    r"^`{32} example[^\n]*\n(.*?)^\.\n.*?^`{32}\n",
    (SPEC_DIR / "gfm-0.29.txt").read_text(encoding="utf-8"),
    re.MULTILINE | re.DOTALL,
)
EXAMPLES = [
    pytest.param(example["markdown"], id=f"commonmark-{example['example']}")
    for example in COMMONMARK
] + [
    pytest.param(markdown.replace("→", "\t"), id=f"gfm-{number}")
    for number, markdown in enumerate(GFM, 1)
]
