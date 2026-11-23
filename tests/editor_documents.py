"""Hand-built editor trees for the canonical round-trip contract."""

import marktip as tm


def node(type_, *children, attrs=None, marks=()):
    result = {"type": type_}
    if children:
        result["content"] = list(children)
    if attrs:
        result["attrs"] = attrs
    if marks:
        result["marks"] = list(marks)
    return result


def text(value, *marks):
    result = node("text", marks=marks)
    result["text"] = value
    return result


def mark(type_, **attrs):
    return node(type_, attrs=attrs)


def paragraph(*children):
    return node("paragraph", *children)


def heading(*children):
    return node("heading", *children, attrs={"level": 2})


def code_block(value, **attrs):
    return node("codeBlock", text(value), attrs=attrs)


def bullet_list(*items, tight=True):
    return node("bulletList", *items, attrs={"tight": tight})


def list_item(*children):
    return node("listItem", *children)


def table(col_count, *rows):
    attrs = {} if col_count is None else {"colCount": col_count}
    return node("table", *(node("tableRow", *row) for row in rows), attrs=attrs)


def cell(*children, header=False, **attrs):
    return node("tableHeader" if header else "tableCell", *children, attrs=attrs)


def case(case_id, *blocks, schema=None, base=None, refuses=False, normalized=None, expected_markdown=None):
    markdown_options = {} if schema is None else {"schema": schema}
    dict_options = dict(markdown_options)
    if base is not None:
        dict_options["base"] = tm.from_markdown(base, **markdown_options)
    return case_id, node("doc", *blocks), dict_options, markdown_options, refuses, normalized, expected_markdown


BOLD = mark("bold")
ITALIC = mark("italic")
STRIKE = mark("strike")
CODE = mark("code")
LINK = mark("link", href="/target")
NOTE = mark("note", label="important")
HARD_BREAK = node("hardBreak")

NOTE_SCHEMA = tm.Schema(marks=[tm.MarkSpec("note", attrs={"label": tm.Attr(str)})])
HEADING_SCHEMA = tm.Schema(core_attrs={"heading": {}})
PARAGRAPH_SCHEMA = tm.Schema(core_attrs={"paragraph": {}})
TABLE_SCHEMA = tm.Schema(core_attrs={"table": {}})
TAGGED_PARAGRAPH_SCHEMA = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})
INLINE_CONTAINER_SCHEMA = tm.Schema(nodes=[tm.NodeSpec("span", "inline", content="inline*")])
MATH_SCHEMA = tm.Schema(nodes=[
    tm.NodeSpec("inlineMath", "inline", math="inline", body="latex", attrs={"latex": tm.Attr(str)}),
])


EDITOR_DOCUMENTS = (
    # Text and lines.
    case("cr-and-crlf-in-text", paragraph(text("a\rb\r\nc"))),
    case("cr-and-crlf-in-code-block", code_block("a\rb\r\nc"), normalized=node("doc", code_block("a\nb\nc"))),
    case("split-crlf-in-code-block", node("codeBlock", text("a\r"), text("\nb")),
         normalized=node("doc", code_block("a\nb"))),
    case("split-crlf-in-code-span-with-empty-link-title",
         paragraph(text("a\r", mark("link", href="/target", title=""), CODE), text("\nb", LINK, CODE)),
         normalized=node("doc", paragraph(text("a b", LINK, CODE)))),
    case("paragraph-line-edge-spaces", paragraph(text(" \tfirst \t\n\tsecond \t")), paragraph(text("word "))),
    case("hard-break-edge-spaces", paragraph(text("first \t"), HARD_BREAK, text("\t second"))),
    case("heading-and-cell-edge-spaces", heading(text(" title \t")),
         table(1, [cell(paragraph(text(" data \t")), header=True)])),
    case("trim-link-marked-edge-spaces", paragraph(text(" label ", LINK)),
         normalized=node("doc", paragraph(text("label", LINK)))),
    case("trim-declared-marked-edge-spaces", paragraph(text(" label ", NOTE)), schema=NOTE_SCHEMA,
         normalized=node("doc", paragraph(text("label", NOTE)))),
    case("consecutive-soft-breaks", paragraph(text("a\n\nb"))),
    case("equal-text-runs-adjacent-after-line-trimming", paragraph(text("a\n"), text("\n", BOLD), text("b")),
         normalized=node("doc", paragraph(text("a\nb")))),
    case("marks-continue-across-trimmed-text",
         paragraph(text("a\n", BOLD), text("\n", ITALIC), text("b", BOLD, ITALIC)),
         normalized=node("doc", paragraph(text("a\n", BOLD), text("b", BOLD, ITALIC)))),
    case("adjacent-raw-inline-html",
         paragraph(text("a"), node("htmlInline", attrs={"html": "<b>"}), node("htmlInline", attrs={"html": "</b>"})),
         normalized=node("doc", paragraph(text("a"), node("htmlInline", attrs={"html": "<b></b>"})))),
    case("paragraph-edge-soft-breaks", paragraph(text("\na\n"))),
    case("soft-breaks-next-to-hard-break", paragraph(text("a\n"), HARD_BREAK, text("\nb"))),
    case("paragraph-edge-hard-breaks", paragraph(HARD_BREAK, text("a"), HARD_BREAK),
         normalized=node("doc", paragraph(HARD_BREAK, text("a")))),
    case("leading-hard-break-in-paragraph", paragraph(HARD_BREAK, text("a")),
         normalized=node("doc", paragraph(HARD_BREAK, text("a")))),
    case("two-leading-hard-breaks-in-paragraph", paragraph(HARD_BREAK, HARD_BREAK, text("a")),
         normalized=node("doc", paragraph(HARD_BREAK, HARD_BREAK, text("a")))),
    case("leading-hard-break-in-list-item", bullet_list(list_item(paragraph(HARD_BREAK, text("a")))),
         normalized=node("doc", bullet_list(list_item(paragraph(HARD_BREAK, text("a")))))),
    case("two-leading-hard-breaks-in-list-item", bullet_list(list_item(paragraph(HARD_BREAK, HARD_BREAK, text("a")))),
         normalized=node("doc", bullet_list(list_item(paragraph(HARD_BREAK, HARD_BREAK, text("a")))))),
    case("trailing-link-marked-hard-break", paragraph(text("a", LINK), node("hardBreak", marks=(LINK,))),
         normalized=node("doc", paragraph(text("a", LINK)))),
    case("trailing-hard-break-in-tagged-paragraph",
         node("paragraph", text("a"), HARD_BREAK, attrs={"textAlign": "center"}), schema=TAGGED_PARAGRAPH_SCHEMA,
         normalized=node("doc", node("paragraph", text("a"), attrs={"textAlign": "center"}))),
    case("table-cell-edge-hard-breaks",
         table(1, [cell(paragraph(HARD_BREAK, text("a"), HARD_BREAK), header=True)]),
         normalized=node("doc", table(1, [cell(paragraph(HARD_BREAK, text("a")), header=True)]))),
    case("blanks-and-soft-break-after-hard-break-in-pipe-cell",
         table(1, [cell(paragraph(text("a"), HARD_BREAK, text(" ", BOLD), text("\nb")), header=True)]),
         normalized=node("doc", table(1, [cell(paragraph(text("a"), HARD_BREAK, text("b")), header=True)]))),
    case("soft-breaks-in-pipe-cell",
         table(1, [cell(paragraph(text("a\nb\n"), HARD_BREAK, text("c")), header=True)]),
         normalized=node("doc", table(1, [cell(paragraph(text("a b "), HARD_BREAK, text("c")), header=True)])),
         expected_markdown="| a b <br>c |\n| --- |"),
    case("newline-in-code-span", paragraph(text("a\nb", CODE))),
    case("code-marked-hard-break", paragraph(text("a", CODE), node("hardBreak", marks=(CODE,)), text("b", CODE)),
         normalized=node("doc", paragraph(text("a", CODE), HARD_BREAK, text("b", CODE)))),
    case("breaks-in-headings", heading(text("a"), HARD_BREAK, text("b")), heading(text("a\nb")),
         normalized=node("doc", heading(text("a b")), heading(text("a b"))), expected_markdown="## a b\n\n## a b"),
    case("breaks-in-tagged-headings", heading(text("a"), HARD_BREAK, text("b")), heading(text("a\nb")),
         schema=HEADING_SCHEMA, normalized=node("doc", heading(text("a"), HARD_BREAK, text("b")), heading(text("a\nb"))),
         expected_markdown="<h2>a\\\nb</h2>\n\n<h2>a\nb</h2>"),

    # Marks and their boundaries.
    case("bold-inside-italic", paragraph(text("italic and ", ITALIC), text("bold", BOLD, ITALIC),
                                       text(" text", ITALIC))),
    case("new-emphasis-marks-in-editor-order", paragraph(text("all", BOLD, ITALIC, STRIKE))),
    case("adjacent-plain-and-marked-text", paragraph(text("a"), text("b "), text("c", BOLD), text("d", BOLD))),
    case("strike-trailing-space", paragraph(text("a"), text("b ", STRIKE), text("c"))),
    case("italic-space-after-bold-letter", paragraph(text("a", BOLD), text(" ", BOLD, ITALIC), text("b"))),
    case("bold-quoted-letter-between-letters", paragraph(text("a"), text('"b"', BOLD), text("c"))),
    case("bold-colon-before-word", paragraph(text("Note:", BOLD), text("text"))),
    case("emphasis-on-hard-break", paragraph(text("a", BOLD), node("hardBreak", marks=(BOLD,)), text("b"))),
    case("link-on-emphasis-edge", paragraph(text("a"), text('"b"', LINK, BOLD), text("c"))),
    case("declared-mark-on-emphasis-edge", paragraph(text("a"), text('"b"', BOLD, NOTE), text("c")),
         schema=NOTE_SCHEMA),
    case("bold-repeated-inside-inline-container",
         paragraph(node("span", text("(x)", BOLD), marks=(BOLD,))), schema=INLINE_CONTAINER_SCHEMA),
    case("link-repeated-inside-inline-container",
         paragraph(node("span", text("x", LINK), marks=(LINK,))), schema=INLINE_CONTAINER_SCHEMA),

    # Blocks and attrs.
    case("empty-list-item", bullet_list(list_item()),
         normalized=node("doc", bullet_list(list_item(paragraph())))),
    case("empty-task-item", node("taskList", node("taskItem", attrs={"checked": True}), attrs={"tight": True}),
         normalized=node("doc", node("taskList", node("taskItem", paragraph(), attrs={"checked": True}),
                                     attrs={"tight": True}))),
    case("empty-table-cell", table(1, [cell(paragraph(text("A")), header=True)], [cell()]),
         normalized=node("doc", table(1, [cell(paragraph(text("A")), header=True)], [cell(paragraph())]))),
    case("empty-blockquote", node("blockquote"), normalized=node("doc", node("blockquote", paragraph()))),
    case("sole-empty-paragraph", paragraph()),
    case("trailing-empty-paragraph", paragraph(text("before")), paragraph()),
    case("trailing-empty-tagged-paragraph", paragraph(text("before")), paragraph(), schema=PARAGRAPH_SCHEMA,
         expected_markdown="before\n\n<p></p>"),
    case("required-empty-paragraph-in-declared-block", node("callout", paragraph()),
         schema=tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="paragraph+")]),
         normalized=node("doc", node("callout", paragraph())), expected_markdown="<callout>\n\n</callout>"),
    case("empty-bullet-list", node("bulletList", attrs={"tight": True})),
    case("empty-table", table(0)),
    case("missing-tight", node("bulletList", list_item(paragraph(text("item"))))),
    case("single-block-loose-list", bullet_list(list_item(paragraph(text("item"))), tight=False)),
    case("tight-list-needing-a-blank-line", bullet_list(list_item(paragraph(text("one")), paragraph(text("two"))))),
    case("tight-list-with-thematic-break", bullet_list(list_item(node("horizontalRule"), paragraph(text("after"))))),
    case("table-without-header-row", table(1, [cell(paragraph(text("one")))],
                                          [cell(paragraph(text("two")), header=True)]),
         normalized=node("doc", table(1, [cell(paragraph(text("one")), header=True)],
                                      [cell(paragraph(text("two")))]))),
    case("table-body-alignment",
         table(2, [cell(paragraph(text("one")), header=True, align="left"), cell(paragraph(text("two")), header=True)],
               [cell(paragraph(text("three")), align="right"), cell(paragraph(text("four")), align="center")]),
         normalized=node("doc", table(2, [cell(paragraph(text("one")), header=True, align="left"),
                                          cell(paragraph(text("two")), header=True)],
                                      [cell(paragraph(text("three")), align="left"), cell(paragraph(text("four")))]))),
    case("table-cell-with-two-paragraphs", table(1, [cell(paragraph(text("one")), header=True)],
                                               [cell(paragraph(text("two")), paragraph(text("three")))]),
         normalized=node("doc", table(1, [cell(paragraph(text("one")), header=True)],
                                      [cell(paragraph(text("two"), HARD_BREAK, text("three")))]))),
    case("trailing-empty-paragraph-in-pipe-cell",
         table(1, [cell(paragraph(text("a")), paragraph(), header=True)]), schema=PARAGRAPH_SCHEMA,
         normalized=node("doc", table(1, [cell(paragraph(text("a")), header=True)])),
         expected_markdown="| a |\n| --- |"),
    case("ragged-table", table(1, [cell(paragraph(text("one")), header=True)],
                              [cell(paragraph(text("two"))), cell(paragraph(text("three")))]),
         normalized=node("doc", table(2, [cell(paragraph(text("one")), header=True), cell(paragraph(), header=True)],
                                      [cell(paragraph(text("two"))), cell(paragraph(text("three")))]))),
    case("ragged-tagged-table", table(3, [cell(paragraph(text("a\nb\n"), HARD_BREAK, text("c")), header=True)],
                                     [cell(paragraph(text("two"))), cell(paragraph(text("three")))]), schema=TABLE_SCHEMA,
         normalized=node("doc", table(2, [cell(paragraph(text("a b "), HARD_BREAK, text("c")), header=True)],
                                      [cell(paragraph(text("two"))), cell(paragraph(text("three")))]))),
    case("missing-list-start-and-task-checked",
         node("orderedList", node("taskItem", paragraph(text("item"))), attrs={"tight": True})),
    case("missing-heading-level", node("heading", text("title"))),
    case("missing-image-alt", paragraph(node("image", attrs={"src": "/image.png"}))),
    case("missing-table-column-count", table(None, [cell(paragraph(text("cell")), header=True)])),
    case("empty-link-and-image-titles", paragraph(text("link", mark("link", href="/target", title="")),
                                                 node("image", attrs={"src": "/image.png", "alt": "", "title": ""}))),
    case("empty-fence-language-and-info", code_block("x\n", language="", info="")),
    case("fence-info-without-language", code_block("x\n", info="python")),
    case("fence-language-disagrees-with-info", code_block("x\n", language="python", info="ruby")),
    case("tab-led-fence-info", code_block("x", info="\tpy options"),
         normalized=node("doc", code_block("x", info="\tpy options"))),

    # Writer spellings.
    case("three-consecutive-hard-breaks", paragraph(text("a"), HARD_BREAK, HARD_BREAK, HARD_BREAK, text("b"))),
    case("all-space-code-span", paragraph(text("  ", CODE))),
    case("pipe-led-table-delimiter-in-paragraph", paragraph(text("a | b\n| --- | --- |"))),
    case("colon-led-table-delimiter-in-paragraph", paragraph(text("a | b\n:--- | ---"))),
    case("plain-url-text", paragraph(text("visit https://example.com today"))),
    case("plain-www-text", paragraph(text("visit www.example.com today"))),
    case("plain-email-text", paragraph(text("write to hello@example.com today"))),
    case("backtick-in-link-destination-before-code-span",
         paragraph(text("link", mark("link", href="/a`b")), text(" "), text("code", CODE))),
    case("empty-link-destination-with-title", paragraph(text("link", mark("link", href="", title="title")))),
    case("fence-info-with-options", code_block("x\n", language="python", info="python numbered")),
    case("code-block-without-final-newline", code_block("x")),
    case("loose-list-with-quote", bullet_list(list_item(paragraph(text("one")),
                                                        node("blockquote", paragraph(text("two")))), tight=False)),

    # Text or structure that strict content will refuse.
    case("touching-strike-inside-italic", paragraph(text("ab"), text("c", ITALIC, STRIKE)), refuses=True),
    case("touching-crossed-bold-and-italic", paragraph(text("a", BOLD), text("b", BOLD, ITALIC), text("c", ITALIC)),
         refuses=True),
    case("heading-in-pipe-table-cell", table(1, [cell(heading(text("title")), header=True)]), refuses=True),
    case("block-image-in-pipe-table-cell",
         table(1, [cell(node("image", attrs={"src": "/b", "alt": "a"}), header=True)]),
         schema=tm.Schema(block_image=True), expected_markdown="| ![a](/b) |\n| --- |"),

    # The remembered table spelling and two atomic node forms.
    case("filled-table-cell-keeps-source",
         table(2, [cell(paragraph(text("Heading")), header=True, align="left"),
                   cell(paragraph(text("B")), header=True, align="right")],
               [cell(paragraph(text("x")), align="left"), cell(paragraph(), align="right")]),
         base="|   Heading   |   B |\n| :-- | ---: |\n| x |    |\n"),
    case("inline-math-and-raw-html", paragraph(node("inlineMath", attrs={"latex": "x + y"}), text(" "),
                                              node("htmlInline", attrs={"html": "<!-- comment -->"})),
         schema=MATH_SCHEMA),
)
