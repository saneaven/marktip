"""Partial input closes declared tags at the end of their parent."""

import pytest

import marktip as tm


def declared_schema():
    return tm.Schema(
        marks=[tm.UNDERLINE, tm.HIGHLIGHT],
        nodes=[
            tm.NodeSpec("callout", "block", content="block+", attrs={"tone": tm.Attr(str)}),
            tm.NodeSpec("summary", "block", content="inline*"),
            tm.NodeSpec("ruby", "inline", content="inline*"),
        ],
    )


OPEN_AND_CLOSED = (
    ("<callout>\n\nbody", "<callout>\n\nbody\n\n</callout>"),
    ("<callout>", "<callout>\n\n</callout>"),
    ("<u>body", "<u>body</u>"),
    ("<u>", "<u></u>"),
    ("<ruby>body", "<ruby>body</ruby>"),
    ("<ruby>", "<ruby></ruby>"),
    ("<summary>body", "<summary>body</summary>"),
    ("<summary>", "<summary></summary>"),
    ("<u>one\n\nafter", "<u>one</u>\n\nafter"),
    ("<ruby>one\n\nafter", "<ruby>one</ruby>\n\nafter"),
    ("<summary>one\n\nafter", "<summary>one</summary>\n\nafter"),
    ("<u>one<mark>two", "<u>one<mark>two</mark></u>"),
    ("<ruby>one<ruby>two", "<ruby>one<ruby>two</ruby></ruby>"),
    ("<callout>\n\n<callout>\n\nbody", "<callout>\n\n<callout>\n\nbody\n\n</callout>\n\n</callout>"),
    ("<callout>\n\n<summary><ruby><u>body",
     "<callout>\n\n<summary><ruby><u>body</u></ruby></summary>\n\n</callout>"),
    ("- <callout>\n  body\n\n- after", "- <callout>\n  body\n  </callout>\n\n- after"),
    ("> <callout>\n> body\n\nafter", "> <callout>\n> body\n> </callout>\n\nafter"),
)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("keep_source", (True, False))
@pytest.mark.parametrize("opening, closed", OPEN_AND_CLOSED)
def test_open_declared_tags_equal_closing_them_at_the_parent_end(opening, closed, html, keep_source):
    schema = declared_schema()
    actual = tm.from_markdown(opening, schema=schema, html=html, partial=True, keep_source=keep_source)
    expected = tm.from_markdown(closed, schema=schema, html=html)
    assert actual.to_dict() == expected.to_dict()


@pytest.mark.parametrize("opening, closed", OPEN_AND_CLOSED)
def test_unclosed_declared_tags_still_fail_by_default(opening, closed):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(opening, schema=declared_schema())
    assert excinfo.value.code == "invalid_tag"


@pytest.mark.parametrize("math, kind, delimiter, expected", (
    ("inline", "inline", "$", {"type": "formula", "attrs": {"html": "x</summary>"}}),
    ("display", "block", "$$", {"type": "text", "text": "$$x</summary>$$"}),
))
def test_partial_textblock_preserves_a_math_body_named_html(math, kind, delimiter, expected):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("summary", "block", content="inline*"),
        tm.NodeSpec("formula", kind, math=math, body="html", attrs={"html": tm.Attr(str)}),
    ])
    markdown = f"<summary>{delimiter}x</summary>{delimiter}"
    actual = tm.from_markdown(markdown, schema=schema, partial=True).to_dict()
    closed = tm.from_markdown(markdown + "</summary>", schema=schema).to_dict()
    assert actual == closed
    assert actual["content"][0]["content"] == [expected]


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown", (
    "<callout>",
    "\n# Before ###\n\n<callout tone='note'>\n*inside*\n\n__last__\n \t\n",
    "<callout>\n[inside]: /inside\n\n<callout>\nbody\n</callout>\n\n[tail]: /tail\n",
))
def test_unclosed_container_keeps_its_exact_source(markdown, html):
    document = tm.from_markdown(markdown, schema=declared_schema(), html=html, partial=True, keep_source=True)
    assert document.to_markdown() == markdown


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown, code", (
    ("</callout>", "invalid_tag"),
    ("</ruby>", "invalid_tag"),
    ("</u>", "invalid_tag"),
    ("<ruby></callout>", "invalid_tag"),
    ("<callout unknown='x'>", "unknown_attr"),
    ("<mark unknown='x'>body", "unknown_attr"),
    ("<callout tone='a' tone='b'>", "invalid_attr_value"),
    ("<u/><ruby>body", "invalid_tag"),
))
def test_partial_keeps_errors_other_than_missing_closing_tags(markdown, code, html):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=declared_schema(), html=html, partial=True)
    assert excinfo.value.code == code


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("closed", (True, False))
def test_partial_keeps_content_model_errors(html, closed):
    schema = tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="paragraph+")])
    markdown = "<callout>\n\n---" + ("\n\n</callout>" if closed else "")
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=schema, html=html, partial=True)
    assert (excinfo.value.code, excinfo.value.field) == ("invalid_content", "content")


@pytest.mark.parametrize("html", (True, False))
def test_partial_keeps_attr_type_errors_in_complete_tags(html):
    schema = tm.Schema(nodes=tm.DETAILS)
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown('<details open="yes">', schema=schema, html=html, partial=True)
    assert (excinfo.value.code, excinfo.value.field) == ("invalid_attr_value", "open")


def readme_schema():
    return tm.Schema(
        marks=[tm.MarkSpec("underline", tag="u")],
        nodes=[tm.NodeSpec("callout", "block", content="block+", attrs={
            "tone": tm.Attr(str, choices=("note", "warning"), default="note"),
        })],
        core_attrs={"paragraph": {"textAlign": tm.Attr(str, choices=("left", "center", "right"))}},
    )


def preset_schema():
    return tm.Schema(
        marks=[tm.UNDERLINE, tm.HIGHLIGHT, tm.SUBSCRIPT, tm.SUPERSCRIPT, tm.TEXT_STYLE],
        nodes=[tm.MENTION, *tm.DETAILS, tm.INLINE_MATH, tm.BLOCK_MATH],
        core_attrs={**tm.TEXT_ALIGN, **tm.LINK_ATTRS, **tm.IMAGE_SIZE, **tm.TABLE_SPANS},
    )


PREFIX_DOCUMENTS = (
    pytest.param('<callout tone="warning">\n\n<u>Read this</u>.\n\n</callout>', readme_schema(), (), id="readme-callout"),
    pytest.param("a <u>x</u> b", readme_schema(), (), id="readme-underline"),
    pytest.param("<ruby>inline content</ruby>", declared_schema(), (), id="readme-inline-container"),
    pytest.param("<summary>inline content</summary>", declared_schema(), (), id="readme-textblock"),
    pytest.param("<embed/>", tm.Schema(nodes=[tm.NodeSpec("embed", "block")]), (), id="readme-block-atom"),
    pytest.param('<p textAlign="center"><u>under</u> <mark color="yellow">high</mark> '
                 '<sub>sub</sub> <sup>sup</sup> <span color="red">styled</span></p>',
                 preset_schema(), (), id="preset-marks-alignment"),
    pytest.param('<h2 textAlign="right">Aligned heading</h2>', preset_schema(), (), id="preset-heading"),
    pytest.param('<a href="/docs" target="_self">Docs</a> <mention id="1" label="Ada"/>',
                 preset_schema(), (), id="preset-link-mention"),
    pytest.param('<img src="logo.png" alt="Logo" width="160" height="80"/>',
                 preset_schema(), (), id="preset-image"),
    pytest.param('<details open="true">\n\n<summary>More</summary>\n\nBody.\n\n</details>',
                 preset_schema(), (), id="preset-details"),
    pytest.param('<inlineMath latex="x^2"/>\n\n<blockMath latex="E = mc^2"/>',
                 preset_schema(), (), id="preset-math-tags"),
    pytest.param('$x^2$\n\n```math\nE = mc^2\n```', preset_schema(), (), id="preset-math-carriers"),
    pytest.param('<table>\n<tr>\n<th colspan="2" colwidth="100,120">\nHeading\n</th>\n</tr>\n'
                 '<tr>\n<td rowspan="2">\nBody\n</td>\n</tr>\n</table>',
                 preset_schema(),
                 (*range(9, 12), *range(14, 48), *range(64, 68), *range(70, 73),
                  *range(75, 90), *range(103, 107), *range(109, 116)), id="preset-table"),
)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("markdown, schema, excluded", PREFIX_DOCUMENTS)
def test_each_declared_document_prefix_parses(markdown, schema, excluded, html):
    # Incomplete table tags become paragraphs that the existing table content model rejects.
    for end in range(len(markdown) + 1):
        if end in excluded:
            with pytest.raises(tm.InvalidNodeError) as excinfo:
                tm.from_markdown(markdown[:end], schema=schema, html=html, partial=True)
            assert excinfo.value.code == "invalid_content"
        else:
            tm.from_markdown(markdown[:end], schema=schema, html=html, partial=True)
    assert tm.from_markdown(markdown, schema=schema, html=html, partial=True).to_dict() == (
        tm.from_markdown(markdown, schema=schema, html=html).to_dict()
    )
