import marktip as tm


def test_parse_heading_marks_and_link():
    assert tm.from_markdown("# Hello\n\nThis is **bold** and [link](https://example.com).\n").to_dict() == {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "This is "},
                    {"type": "text", "text": "bold", "marks": [{"type": "bold"}]},
                    {"type": "text", "text": " and "},
                    {
                        "type": "text",
                        "text": "link",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                    },
                    {"type": "text", "text": "."},
                ],
            },
        ],
    }


def test_parse_collapses_nested_same_type_spans_into_one_self_exclusive_mark():
    cases = [
        ("****x****", "x", "bold"),
        ("*outer _inner_ outer*", "outer inner outer", "italic"),
        ("**outer __inner__ outer**", "outer inner outer", "bold"),
        ("~~outer ~~inner~~ outer~~", "outer inner outer", "strike"),
    ]

    for markdown, expected_text, mark_type in cases:
        content = tm.from_markdown(markdown).to_dict()["content"][0]["content"]
        assert content == [
            {"type": "text", "text": expected_text, "marks": [{"type": mark_type}]},
        ]

    content = tm.from_markdown("*outer _inner_ outer* plain").to_dict()["content"][0]["content"]
    assert content == [
        {"type": "text", "text": "outer inner outer", "marks": [{"type": "italic"}]},
        {"type": "text", "text": " plain"},
    ]


def test_parse_gfm_task_list_and_table():
    ast = tm.from_markdown("- [x] done\n- [ ] todo\n\n| A | B |\n| :- | -: |\n| x | y |\n").to_dict()

    task_list = ast["content"][0]
    assert task_list["type"] == "taskList"
    assert task_list["content"][0]["attrs"] == {"checked": True}
    assert task_list["content"][1]["attrs"] == {"checked": False}

    table = ast["content"][1]
    assert table["type"] == "table"
    assert table["attrs"] == {"colCount": 2}
    assert table["content"][0]["content"][0]["type"] == "tableHeader"
    assert table["content"][0]["content"][0]["attrs"] == {"align": "left"}
    assert table["content"][0]["content"][1]["attrs"] == {"align": "right"}


def test_parse_raw_html_code_image_and_breaks():
    ast = tm.from_markdown(
        '<div>raw</div>\n\n'
        'Hello <span>x</span>!\n\n'
        '![Alt *text*](img.png "Title")\n\n'
        '```cpp\nint main() { return 0; }\n```\n\n'
        'a  \nb\n'
    ).to_dict()

    assert ast["content"][0] == {"type": "htmlBlock", "attrs": {"html": "<div>raw</div>\n"}}
    assert ast["content"][1]["content"][1] == {"type": "htmlInline", "attrs": {"html": "<span>"}}
    assert ast["content"][2]["content"][0] == {
        "type": "image",
        "attrs": {"src": "img.png", "title": "Title", "alt": "Alt text"},
    }
    assert ast["content"][3]["type"] == "codeBlock"
    assert ast["content"][3]["attrs"] == {"language": "cpp", "info": "cpp"}
    assert ast["content"][4]["content"][1] == {"type": "hardBreak"}


def test_parse_decodes_entities():
    ast = tm.from_markdown("&copy; &amp; &#65; &#x1F600;").to_dict()

    assert ast["content"][0]["content"][0]["text"] == "© & A \U0001F600"


def test_parse_maps_br_in_table_cell_to_hard_break():
    ast = tm.from_markdown("| A |\n| - |\n| x<br>y |\n").to_dict()

    cell = ast["content"][0]["content"][1]["content"][0]["content"][0]
    assert cell["content"] == [
        {"type": "text", "text": "x"},
        {"type": "hardBreak"},
        {"type": "text", "text": "y"},
    ]


def test_parse_cjk_friendly_is_opt_in():
    md = "**마크다운(Markdown)**은 표준이다"

    relaxed = tm.from_markdown(md, cjk_friendly=True).to_dict()
    assert relaxed["content"][0]["content"][0] == {
        "type": "text",
        "text": "마크다운(Markdown)",
        "marks": [{"type": "bold"}],
    }

    standard = tm.from_markdown(md).to_dict()
    assert standard["content"][0]["content"][0]["text"].startswith("**")


def test_parse_accepts_bytes():
    assert tm.from_markdown(b"# Bytes").to_dict()["content"][0]["content"][0]["text"] == "Bytes"


def _strike_texts(md, **kwargs):
    ast = tm.from_markdown(md, **kwargs).to_dict()
    found = []

    def walk(node):
        if node.get("type") == "text" and any(
            mark["type"] == "strike" for mark in node.get("marks", [])
        ):
            found.append(node["text"])
        for child in node.get("content", []):
            walk(child)

    walk(ast)
    return found


def test_parse_intraword_strikethrough_matches_gfm():
    # cmark-gfm treats `~` like `*`, so intra-word `~~` strikes; upstream md4c
    # rejects it. The local tilde patch aligns default parsing with cmark-gfm.
    assert _strike_texts("a~~b~~c") == ["b"]
    assert _strike_texts("a~~b~~c", cjk_friendly=True) == ["b"]
    # Regressions: existing behavior stays put.
    assert _strike_texts("~~x~~") == ["x"]
    assert _strike_texts("a ~~b~~ c") == ["b"]
    assert _strike_texts("a~~ b~~") == []  # space after the opener still blocks
    assert _strike_texts("x ~~~y~~~") == []  # runs longer than 2 never match
    assert _strike_texts("~foo~~") == []  # opener/closer lengths must agree


def test_parse_strike_next_to_cjk_letters_works_by_default():
    # CJK letters are neither whitespace nor punctuation, so with the graded
    # rules `~~삭제~~은` strikes under default parsing too (same as cmark-gfm).
    assert _strike_texts("~~삭제~~은") == ["삭제"]
    # Punctuation-adjacent cases still need the cjk_friendly relaxation.
    assert _strike_texts('~~"인용"~~라고') == []
    assert _strike_texts('~~"인용"~~라고', cjk_friendly=True) == ['"인용"']


def test_parse_html_disabled_turns_raw_html_into_text():
    block = tm.from_markdown("<div>raw</div>", html=False).to_dict()
    assert block["content"] == [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "<div>raw</div>"}],
        }
    ]

    inline = tm.from_markdown("Hello <span>x</span>!", html=False).to_dict()
    assert inline["content"][0]["content"] == [
        {"type": "text", "text": "Hello <span>x</span>!"}
    ]


def test_parse_html_disabled_keeps_br_in_table_cell():
    # The serializer expresses cell hard breaks as <br>, so that mapping must
    # survive html=False for marktip's own output to round-trip.
    ast = tm.from_markdown("| A |\n| - |\n| x<br>y |\n", html=False).to_dict()

    cell = ast["content"][0]["content"][1]["content"][0]["content"][0]
    assert cell["content"] == [
        {"type": "text", "text": "x"},
        {"type": "hardBreak"},
        {"type": "text", "text": "y"},
    ]
