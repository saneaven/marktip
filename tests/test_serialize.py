import pytest

import marktip as tm


def test_serialize_hand_written_tiptap_doc():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "API"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Fast", "marks": [{"type": "italic"}]},
                    {"type": "text", "text": " "},
                    {"type": "text", "text": "parser", "marks": [{"type": "bold"}]},
                    {"type": "text", "text": " at "},
                    {
                        "type": "text",
                        "text": "home",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                    },
                    {"type": "hardBreak"},
                    {"type": "image", "attrs": {"src": "logo.png", "alt": "Logo"}},
                ],
            },
        ],
    }

    assert tm.from_dict(ast).to_markdown() == "## API\n\n*Fast* **parser** at [home](https://example.com)  \n![Logo](logo.png)"


def test_serialize_lists_code_and_table():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "taskList",
                "content": [
                    {"type": "taskItem", "attrs": {"checked": True}, "content": [{"type": "text", "text": "ship"}]},
                    {"type": "taskItem", "attrs": {"checked": False}, "content": [{"type": "text", "text": "write tests"}]},
                ],
            },
            {"type": "codeBlock", "attrs": {"language": "cpp"}, "content": [{"type": "text", "text": "return 0;\n"}]},
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {"type": "tableHeader", "attrs": {"align": "left"}, "content": [{"type": "text", "text": "A"}]},
                            {"type": "tableHeader", "attrs": {"align": "right"}, "content": [{"type": "text", "text": "B"}]},
                        ],
                    },
                    {
                        "type": "tableRow",
                        "content": [
                            {"type": "tableCell", "content": [{"type": "text", "text": "x|y"}]},
                            {"type": "tableCell", "content": [{"type": "text", "text": "z"}]},
                        ],
                    },
                ],
            },
        ],
    }

    assert tm.from_dict(ast).to_markdown() == (
        "- [x] ship\n"
        "- [ ] write tests\n\n"
        "```cpp\n"
        "return 0;\n"
        "```\n\n"
        "| A | B |\n"
        "| :--- | ---: |\n"
        "| x\\|y | z |"
    )


def test_serialize_rejects_non_doc_root():
    with pytest.raises(ValueError, match="root node"):
        tm.from_dict({"type": "paragraph"})
