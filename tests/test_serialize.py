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
    with pytest.raises(tm.InvalidNodeError, match="root node"):
        tm.from_dict({"type": "paragraph"})


def test_serialize_escapes_raw_html_and_entities_in_text():
    ast = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "a <b> &amp; c"}]},
        ],
    }

    assert tm.from_markdown(tm.from_dict(ast).to_markdown()).to_dict() == ast


def test_serialize_hard_break_in_table_cell_as_br():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [{"type": "tableHeader", "content": [{"type": "text", "text": "h"}]}],
                    },
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "line1"},
                                            {"type": "hardBreak"},
                                            {"type": "text", "text": "line2"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }

    markdown = tm.from_dict(ast).to_markdown()
    assert markdown.splitlines()[-1] == "| line1<br>line2 |"

    reparsed_cell = tm.from_markdown(markdown).to_dict()["content"][0]["content"][1]["content"][0]
    assert reparsed_cell["content"][0]["content"] == [
        {"type": "text", "text": "line1"},
        {"type": "hardBreak"},
        {"type": "text", "text": "line2"},
    ]


def doc_with(node):
    return tm.from_dict({"type": "doc", "content": [node]}).to_markdown()


def test_html_nodes_fall_back_to_content_when_attr_is_absent():
    # from_dict accepts and stores content on html nodes, so dropping it here would be
    # the silent loss the closed schema exists to prevent.
    # plain_text used to answer with the "html" attr for these types,
    # which made the attr's own fallback recurse straight back to "".
    assert doc_with({"type": "htmlBlock", "content": [{"type": "text", "text": "<div>hi</div>"}]}) == "<div>hi</div>"

    inline = {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": "a"},
            {"type": "htmlInline", "content": [{"type": "text", "text": "<u>U</u>"}]},
            {"type": "text", "text": "b"},
        ],
    }
    assert doc_with(inline) == "a<u>U</u>b"


def test_html_attr_wins_over_content():
    node = {
        "type": "htmlBlock",
        "attrs": {"html": "<b>A</b>"},
        "content": [{"type": "text", "text": "ignored"}],
    }
    assert doc_with(node) == "<b>A</b>"


def test_explicit_empty_html_attr_stays_empty():
    # The key is present, so "" is a deliberate value rather than a missing payload.
    node = {"type": "htmlBlock", "attrs": {"html": ""}, "content": [{"type": "text", "text": "x"}]}
    assert doc_with(node) == ""
    assert doc_with({"type": "htmlBlock"}) == ""


def test_image_alt_falls_back_to_content():
    node = {
        "type": "paragraph",
        "content": [{"type": "image", "attrs": {"src": "i.png"}, "content": [{"type": "text", "text": "ALT"}]}],
    }
    assert doc_with(node) == "![ALT](i.png)"


def ordered(start):
    item = {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}]}
    return doc_with({"type": "orderedList", "attrs": {"start": start}, "content": [item, dict(item)]})


@pytest.mark.parametrize(
    "start, first",
    [
        (1, "1."),
        (0, "0."),
        (-5, "0."),  # "-5. a" is not a list at all on reparse
        (999999999, "999999999."),
        (10**12, "999999999."),  # a 10-digit marker stops being a list marker
    ],
)
def test_ordered_list_start_is_clamped_to_the_commonmark_range(start, first):
    assert ordered(start).startswith(first + " a\n")


def test_ordered_list_numbering_stops_at_the_ceiling():
    # Only the first number is honoured on reparse, so repeating it changes nothing.
    assert ordered(999999999) == "999999999. a\n999999999. a"


def code_block(language, code="q"):
    return doc_with({"type": "codeBlock", "attrs": {"language": language}, "content": [{"type": "text", "text": code}]})


def test_code_fence_info_is_truncated_at_the_first_newline():
    # The tail used to land in the fence body, so the code gained a line on reparse.
    assert code_block("py\nx") == "```py\nq\n```"
    assert code_block("py\r\nx") == "```py\nq\n```"


def test_code_fence_switches_to_tildes_when_the_language_holds_a_backtick():
    # A backtick closes a backtick fence. Tildes carry the same info string losslessly.
    assert code_block("py`x") == "~~~py`x\nq\n~~~"
    assert code_block("py`x", "~~~ inside") == "~~~~py`x\n~~~ inside\n~~~~"
    assert code_block("py", "``` inside") == "````py\n``` inside\n````"
