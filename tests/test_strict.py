"""Opt-in strict mode: refuse instead of silently altering the document.

Issue #3 — node and mark *types* are closed, but attrs are not. An attr the serializer
never reads is dropped without a word, so a `colspan: 2` cell quietly becomes a plain
one and `start: -5` renders as something that is not a list at all.

Checking that in Python means walking the tree a second time, after marktip already
walked it in C++. strict=True does it from the walk that is already happening.

It is from_dict-only, unlike the URI policy: the parser only ever emits attrs it
understands, with values in range, so there is nothing on the from_markdown path for it
to catch. test_strict_accepts_what_the_parser_produces is the guard on that claim.
"""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x"):
    return {"type": "text", "text": value}


def node(type_, **attrs):
    return {"type": type_, "attrs": attrs, "content": [p(text())]}


def cell(**attrs):
    return doc({"type": "table", "content": [{"type": "tableRow", "content": [node("tableCell", **attrs)]}]})


def link(**attrs):
    return doc(p({"type": "text", "text": "x", "marks": [{"type": "link", "attrs": attrs}]}))


def ordered(**attrs):
    return doc({"type": "orderedList", "attrs": attrs, "content": [{"type": "listItem", "content": [p(text("a"))]}]})


def code_block(**attrs):
    return doc({"type": "codeBlock", "attrs": attrs, "content": [text("q")]})


# Where a violation is reported, for each of the shapes above.
CELL_PATH = "content[0].content[0].content[0]"
LINK_PATH = "content[0].content[0].marks[0]"


def code_for(ast, **options):
    """The .code from converting `ast`, or None when it is accepted."""
    try:
        tm.from_dict(ast, **options).to_markdown()
    except tm.MarktipError as err:
        return err.code
    return None


# ── the default: nothing changes for anyone not asking for it ────────────────


@pytest.mark.parametrize(
    "ast",
    [
        cell(colspan=2),
        cell(colwidth=[100]),
        cell(foo="bar"),
        cell(align="middle"),
        link(href="https://a", onclick="evil()"),
        doc(node("heading", level=9)),
        ordered(start=-5),
        code_block(language="py\nx"),
    ],
)
def test_documents_that_convert_today_still_convert(ast):
    # marktip is a converter first. Every one of these is accepted, and lossily, which is
    # exactly what strict exists to surface — but only when asked.
    assert code_for(ast) is None


def test_strict_is_off_by_default():
    assert code_for(cell(colspan=2)) is None
    assert code_for(cell(colspan=2), strict=True) == "unrepresentable"


# ── unknown_attr: no markdown form for this type ─────────────────────────────


def test_unknown_node_attr_reports_code_field_and_path():
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(cell(foo="bar"), strict=True)

    err = excinfo.value
    assert err.code == "unknown_attr"
    assert err.field == "foo"
    assert err.path == CELL_PATH
    assert str(err) == "attr 'foo' is not defined for node type 'tableCell'"
    assert err.detail == str(err)


@pytest.mark.parametrize("attr", ["target", "rel", "class", "onclick"])
def test_tiptap_link_extension_attrs_have_no_markdown_form(attr):
    # The Link extension emits target/rel by default, so this is the first thing a
    # consumer turning strict on will hit. It is also the case the issue asks for:
    # onclick="evil()" must not vanish silently.
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(link(href="https://a", **{attr: "_blank"}), strict=True)

    assert excinfo.value.code == "unknown_attr"
    assert excinfo.value.field == attr
    assert excinfo.value.path == LINK_PATH
    assert "mark type 'link'" in str(excinfo.value)


def test_attrs_are_scoped_to_their_own_type():
    # level belongs to heading, not to paragraph; tight to a list, not to its items.
    assert code_for(doc(node("heading", level=2)), strict=True) is None
    assert code_for(doc({"type": "paragraph", "attrs": {"level": 2}}), strict=True) == "unknown_attr"
    assert code_for(doc({"type": "bulletList", "attrs": {"tight": True}}), strict=True) is None
    assert code_for(doc({"type": "listItem", "attrs": {"tight": True}}), strict=True) == "unknown_attr"


# ── invalid_attr_value: known name, wrong type or out of range ───────────────


@pytest.mark.parametrize(
    "level, expected",
    [
        (1, None),
        (6, None),
        (0, "invalid_attr_value"),
        (7, "invalid_attr_value"),
        (-1, "invalid_attr_value"),
        ("2", "invalid_attr_value"),
        (2.0, "invalid_attr_value"),
        (True, "invalid_attr_value"),  # bool is an int subclass in Python; a level is not a bool
        (10**100, "invalid_attr_value"),  # too large for long long — a document problem, not an OverflowError
    ],
)
def test_heading_level_range(level, expected):
    assert code_for(doc(node("heading", level=level)), strict=True) == expected


@pytest.mark.parametrize(
    "start, expected",
    [
        (0, None),
        (1, None),
        (999999999, None),
        (-5, "invalid_attr_value"),  # renders as "-5. a", which reparses as a paragraph
        (1000000000, "invalid_attr_value"),  # a 10-digit marker is not a list marker
        ("1", "invalid_attr_value"),
    ],
)
def test_ordered_list_start_range(start, expected):
    assert code_for(ordered(start=start), strict=True) == expected


@pytest.mark.parametrize("value, expected", [(True, None), (False, None), (1, "invalid_attr_value"), ("yes", "invalid_attr_value")])
def test_bool_attrs_are_not_coerced_under_strict(value, expected):
    assert code_for(doc({"type": "taskList", "attrs": {"tight": value}}), strict=True) == expected


@pytest.mark.parametrize(
    "language, expected",
    [
        ("py", None),
        ("", None),
        ("py`x", None),  # lossless: the serializer switches to a ~~~ fence
        ("py\nx", "invalid_attr_value"),  # would push "x" into the code content on reparse
        ("py\rx", "invalid_attr_value"),
        (1, "invalid_attr_value"),
    ],
)
def test_code_fence_info_must_be_a_single_line(language, expected):
    assert code_for(code_block(language=language), strict=True) == expected


@pytest.mark.parametrize(
    "align, expected",
    [("left", None), ("center", None), ("right", None), (None, None), ("middle", "invalid_attr_value"), ("", "invalid_attr_value")],
)
def test_cell_align_values(align, expected):
    assert code_for(cell(align=align), strict=True) == expected


def test_invalid_value_reports_the_attr_as_field():
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(node("heading", level=9)), strict=True)

    err = excinfo.value
    assert err.code == "invalid_attr_value"
    assert err.field == "level"
    assert err.path == "content[0]"
    assert str(err) == "attr 'level' must be an int between 1 and 6"


# ── unrepresentable: well-formed, but GFM cannot carry it ────────────────────


def test_tiptap_table_defaults_are_accepted():
    # The table extension puts these on every cell. Refusing the *names* would leave
    # strict unusable for the consumer that asked for it, so only non-no-op values fail.
    assert code_for(cell(colspan=1, rowspan=1, colwidth=None), strict=True) is None


@pytest.mark.parametrize(
    "attrs, field",
    [
        ({"colspan": 2}, "colspan"),
        ({"rowspan": 3}, "rowspan"),
        ({"colspan": 0}, "colspan"),
        ({"colwidth": [100]}, "colwidth"),
        ({"colwidth": [100, 200]}, "colwidth"),
    ],
)
def test_table_features_gfm_cannot_express(attrs, field):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(cell(**attrs), strict=True)

    err = excinfo.value
    assert err.code == "unrepresentable"
    assert err.field == field
    assert err.path == CELL_PATH
    assert "cannot be expressed in markdown" in str(err)


def test_unrepresentable_is_distinct_from_a_malformed_value():
    # Different remediation for the caller: colspan=2 is a valid Tiptap document that
    # markdown cannot carry, level=9 is simply wrong.
    assert code_for(cell(colspan=2), strict=True) == "unrepresentable"
    assert code_for(doc(node("heading", level=9)), strict=True) == "invalid_attr_value"


# ── the two attrs that are accepted and ignored ──────────────────────────────


def test_col_count_and_body_row_align_are_accepted_though_unused():
    # The serializer derives the column count from the rows and reads align only from the
    # header row. Both are still accepted, because from_markdown emits both — see
    # test_strict_accepts_what_the_parser_produces for why that matters.
    assert code_for(doc({"type": "table", "attrs": {"colCount": 2}}), strict=True) is None
    body = doc(
        {
            "type": "table",
            "content": [
                {"type": "tableRow", "content": [node("tableHeader", align="left")]},
                {"type": "tableRow", "content": [node("tableCell", align="right")]},
            ],
        }
    )
    assert code_for(body, strict=True) is None


def test_col_count_is_still_an_int():
    assert code_for(doc({"type": "table", "attrs": {"colCount": -1}}), strict=True) == "invalid_attr_value"
    assert code_for(doc({"type": "table", "attrs": {"colCount": "2"}}), strict=True) == "invalid_attr_value"


# ── the invariant that keeps the two exceptions above honest ─────────────────


PARSER_CORPUS = [
    "# h1\n\n## h2\n\ntext with **bold**, *em*, `code` and ~~strike~~\n",
    "| a | b | c |\n| :-- | :-: | --: |\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n",
    "- a\n- b\n  - nested\n\n1. one\n2. two\n\n5. five\n",
    "- [ ] todo\n- [x] done\n",
    "> quote\n>\n> > nested\n",
    "```py\nprint(1)\n```\n\n~~~py`x\ninfo string with a backtick\n~~~\n",
    '[link](https://a.example "t") and ![img](i.png "cap")\n',
    "<div>raw</div>\n\ntext <span>inline</span> more\n",
    "---\n\npara with  \nhard break\n",
    "999999998. a\n999999999. b\n",
]


@pytest.mark.parametrize("markdown", PARSER_CORPUS)
def test_strict_accepts_what_the_parser_produces(markdown):
    # A consumer that stores canonical markdown re-parses it on the read path (issue #1).
    # If strict rejected marktip's own output, that path would break on rows that were
    # written successfully — the failure mode that is hardest to notice.
    parsed = tm.from_markdown(markdown)
    assert tm.from_dict(parsed.to_dict(), strict=True).to_markdown() == parsed.to_markdown()


# ── surface ──────────────────────────────────────────────────────────────────


def test_strict_is_keyword_only():
    with pytest.raises(TypeError):
        tm.from_dict(doc(p(text())), True)


def test_strict_composes_with_the_uri_policy():
    ast = link(href="javascript:alert(1)", target="_blank")
    assert code_for(ast, link_schemes=("https",)) == "disallowed_scheme"
    assert code_for(ast, strict=True) == "unknown_attr"
    assert code_for(link(href="javascript:alert(1)"), strict=True, link_schemes=("https",)) == "disallowed_scheme"


def test_every_violation_is_a_marktip_error():
    for ast in [cell(foo="bar"), cell(colspan=2), doc(node("heading", level=9))]:
        with pytest.raises(tm.MarktipError):
            tm.from_dict(ast, strict=True)
