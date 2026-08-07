"""Opt-in strict levels: name what the conversion may not lose.

Issue #3 — node and mark *types* are closed, but attrs are not. An attr the serializer
never reads is dropped without a word, so a `colspan: 2` cell quietly becomes a plain
one and `start: -5` renders as something that is not a list at all.

Checking that in Python means walking the tree a second time, after marktip already
walked it in C++. strict does it from the walk that is already happening.

There are two levels rather than one because losses are not all the same kind (#5). A
colspan the serializer drops moves every cell after it under a different header; a link
target it drops costs the author nothing, because the editor stamped it on and nobody
wrote it. Nothing in the JSON tells those apart — ProseMirror serializes schema defaults
onto every node — so the caller says which loss is acceptable: "content" or "exact".

It is from_dict-only, unlike the URI policy: the parser only ever emits attrs it
understands, with values in range, so there is nothing on the from_markdown path for it
to catch. test_strict_accepts_what_the_parser_produces is the guard on that claim.

Issue #8 adds the collection-level half of that promise: when strict validation is
enabled, self-exclusive ProseMirror marks cannot repeat on a node. With strict="off",
that validation is intentionally not performed.
"""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x"):
    return {"type": "text", "text": value}


def marked(*marks):
    return doc(p({"type": "text", "text": "x", "marks": list(marks)}))


def mark(type_, **attrs):
    value = {"type": type_}
    if attrs:
        value["attrs"] = attrs
    return value


def node(type_, **attrs):
    return {"type": type_, "attrs": attrs, "content": [p(text())]}


def cell(**attrs):
    return doc({"type": "table", "content": [{"type": "tableRow", "content": [node("tableCell", **attrs)]}]})


def link(**attrs):
    return doc(p({"type": "text", "text": "x", "marks": [{"type": "link", "attrs": attrs}]}))


def image(**attrs):
    return doc(p({"type": "image", "attrs": attrs}))


def captioned_image(**attrs):
    return doc(p({"type": "image", "attrs": attrs, "content": [text("cap")]}))


def ordered(**attrs):
    return doc({"type": "orderedList", "attrs": attrs, "content": [{"type": "listItem", "content": [p(text("a"))]}]})


def code_block(**attrs):
    return doc({"type": "codeBlock", "attrs": attrs, "content": [text("q")]})


# Where a violation is reported, for each of the shapes above.
CELL_PATH = "content[0].content[0].content[0]"
LINK_PATH = "content[0].content[0].marks[0]"
IMAGE_PATH = "content[0].content[0]"
SECOND_MARK_PATH = "content[0].content[0].marks[1]"

# Both levels checked everywhere the two are meant to agree, which is everywhere but
# the presentation attrs below. A rule that only ever ran at one level would be a rule
# whose level nobody chose.
LEVELS = ["content", "exact"]


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
        link(),
        image(),
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
    assert code_for(cell(colspan=2), strict="content") == "unrepresentable"


# ── invalid_mark_set: self-exclusive marks cannot repeat ────────────────────


DUPLICATE_MARK_CASES = [
    pytest.param([mark("bold"), mark("bold")], id="bold"),
    pytest.param([mark("italic"), mark("italic")], id="italic"),
    pytest.param([mark("strike"), mark("strike")], id="strike"),
    pytest.param([mark("code"), mark("code")], id="code"),
    pytest.param(
        [mark("link", href="https://a.example"), mark("link", href="https://a.example")],
        id="identical-link",
    ),
    pytest.param(
        [mark("link", href="https://a.example"), mark("link", href="https://b.example")],
        id="conflicting-link",
    ),
]


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("marks", DUPLICATE_MARK_CASES)
def test_strict_rejects_duplicate_same_type_marks(level, marks):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(*marks), strict=level)

    err = excinfo.value
    assert err.code == "invalid_mark_set"
    assert err.field == "marks"
    assert err.path == SECOND_MARK_PATH
    assert str(err) == f"mark type '{marks[1]['type']}' conflicts with an earlier mark of the same type"
    assert err.detail == str(err)


@pytest.mark.parametrize("marks", DUPLICATE_MARK_CASES)
def test_mark_set_validation_is_skipped_when_strict_is_off(marks):
    # Off means the strict mark-set check is disabled; accepting these inputs is
    # the option's semantics, not a compatibility exception.
    ast = marked(*marks)
    document = tm.from_dict(ast, strict="off")
    assert document.to_dict() == ast
    assert isinstance(document.to_markdown(), str)


@pytest.mark.parametrize("level", LEVELS)
def test_strict_reports_a_nonadjacent_duplicate_at_the_conflicting_mark(level):
    ast = marked(mark("italic"), mark("bold"), mark("italic"))

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.path == "content[0].content[0].marks[2]"


@pytest.mark.parametrize("level", LEVELS)
def test_strict_checks_mark_sets_on_non_text_inline_nodes(level):
    ast = doc(
        p(
            {
                "type": "image",
                "attrs": {"src": "x.png"},
                "marks": [mark("link", href="https://a.example"), mark("link", href="https://b.example")],
            }
        )
    )

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", LEVELS)
def test_strict_allows_distinct_mark_types_and_reuse_on_another_node(level):
    ast = doc(
        p(
            {"type": "text", "text": "a", "marks": [mark("italic"), mark("bold")]},
            {"type": "text", "text": "b", "marks": [mark("bold"), mark("italic")]},
            {"type": "text", "text": "c", "marks": [mark("italic"), mark("link", href="https://a.example")]},
        )
    )

    assert code_for(ast, strict=level) is None


@pytest.mark.parametrize("level", LEVELS)
def test_an_invalid_duplicate_mark_is_reported_before_the_set_conflict(level):
    ast = marked(mark("link", href="https://a.example"), mark("link"))

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    assert excinfo.value.code == "missing_attr"
    assert excinfo.value.field == "href"
    assert excinfo.value.path == SECOND_MARK_PATH


# ── unknown_attr: a name outside both dialects ───────────────────────────────


@pytest.mark.parametrize("level", LEVELS)
def test_unknown_node_attr_reports_code_field_and_path(level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(cell(foo="bar"), strict=level)

    err = excinfo.value
    assert err.code == "unknown_attr"
    assert err.field == "foo"
    assert err.path == CELL_PATH
    assert str(err) == "attr 'foo' is not defined for node type 'tableCell'"
    assert err.detail == str(err)


@pytest.mark.parametrize("level", LEVELS)
def test_a_name_no_schema_declares_is_refused_at_every_level(level):
    # The case that earns the check its keep: onclick="evil()" must not vanish silently,
    # and no Tiptap extension in marktip's dialect declares it, so nothing is lost by saying so.
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(link(href="https://a", onclick="evil()"), strict=level)

    assert excinfo.value.code == "unknown_attr"
    assert excinfo.value.field == "onclick"
    assert excinfo.value.path == LINK_PATH
    assert "mark type 'link'" in str(excinfo.value)


@pytest.mark.parametrize("level", LEVELS)
def test_attrs_are_scoped_to_their_own_type(level):
    # level belongs to heading, not to paragraph; tight to a list, not to its items.
    assert code_for(doc(node("heading", level=2)), strict=level) is None
    assert code_for(doc({"type": "paragraph", "attrs": {"level": 2}}), strict=level) == "unknown_attr"
    assert code_for(doc({"type": "bulletList", "attrs": {"tight": True}}), strict=level) is None
    assert code_for(doc({"type": "listItem", "attrs": {"tight": True}}), strict=level) == "unknown_attr"


# ── invalid_attr_value: known name, wrong type or out of range ───────────────


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "value, expected",
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
def test_heading_level_range(value, expected, level):
    assert code_for(doc(node("heading", level=value)), strict=level) == expected


@pytest.mark.parametrize("level", LEVELS)
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
def test_ordered_list_start_range(start, expected, level):
    assert code_for(ordered(start=start), strict=level) == expected


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "value, expected", [(True, None), (False, None), (1, "invalid_attr_value"), ("yes", "invalid_attr_value")]
)
def test_bool_attrs_are_not_coerced_under_strict(value, expected, level):
    assert code_for(doc({"type": "taskList", "attrs": {"tight": value}}), strict=level) == expected


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "language, expected",
    [
        ("py", None),
        ("", None),
        ("py`x", None),  # lossless: the serializer switches to a ~~~ fence
        ("py\nx", "invalid_attr_value"),  # would push "x" into the code content on reparse
        ("py\rx", "invalid_attr_value"),
        (1, "invalid_attr_value"),
        (None, None),  # unset, not a wrong type — see below
    ],
)
def test_code_fence_info_must_be_a_single_line(language, expected, level):
    assert code_for(code_block(language=language), strict=level) == expected


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "align, expected",
    [
        ("left", None),
        ("center", None),
        ("right", None),
        (None, None),
        ("middle", "invalid_attr_value"),
        ("", "invalid_attr_value"),
    ],
)
def test_cell_align_values(align, expected, level):
    assert code_for(cell(align=align), strict=level) == expected


@pytest.mark.parametrize("level", LEVELS)
def test_invalid_value_reports_the_attr_as_field(level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(node("heading", level=9)), strict=level)

    err = excinfo.value
    assert err.code == "invalid_attr_value"
    assert err.field == "level"
    assert err.path == "content[0]"
    assert str(err) == "attr 'level' must be an int between 1 and 6"


# ── unrepresentable: well-formed, but GFM cannot carry it ────────────────────


@pytest.mark.parametrize("level", LEVELS)
def test_tiptap_table_no_op_defaults_are_accepted(level):
    # The table extension puts these on every cell. Refusing the *names* would leave
    # strict unusable for the consumer that asked for it, and a span of 1 is no span at all,
    # so there is nothing to lose by taking them.
    assert code_for(cell(colspan=1, rowspan=1), strict=level) is None


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("attrs, field", [({"colspan": 2}, "colspan"), ({"rowspan": 3}, "rowspan"), ({"colspan": 0}, "colspan")])
def test_structure_gfm_cannot_express_is_refused_at_every_level(attrs, field, level):
    # Not presentation: dropping a colspan shifts every cell after it under a different
    # header, so the loss reaches the content itself. Both levels refuse it.
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(cell(**attrs), strict=level)

    err = excinfo.value
    assert err.code == "unrepresentable"
    assert err.field == field
    assert err.path == CELL_PATH
    assert "cannot be expressed in markdown" in str(err)


@pytest.mark.parametrize("level", LEVELS)
def test_unrepresentable_is_distinct_from_a_malformed_value(level):
    # Different remediation for the caller: colspan=2 is a valid Tiptap document that
    # markdown cannot carry, level=9 is simply wrong.
    assert code_for(cell(colspan=2), strict=level) == "unrepresentable"
    assert code_for(doc(node("heading", level=9)), strict=level) == "invalid_attr_value"


# ── content vs exact: the presentation an editor stamps on ───────────────────


# Every attr a stock Tiptap schema declares that markdown has no form for, at a value
# someone could plausibly have chosen. Issue #5 is that "content" has to take all of these.
PRESENTATION = [
    (link(href="https://a", target="_blank"), "target", LINK_PATH),
    (link(href="https://a", rel="noopener noreferrer nofollow"), "rel", LINK_PATH),
    (link(href="https://a", **{"class": "external"}), "class", LINK_PATH),
    (image(src="a.png", width=300), "width", IMAGE_PATH),
    (image(src="a.png", height="200"), "height", IMAGE_PATH),
    (ordered(type="a"), "type", "content[0]"),
    (cell(colwidth=[100, 200]), "colwidth", CELL_PATH),
]


@pytest.mark.parametrize("ast, field, path", PRESENTATION)
def test_content_takes_presentation_and_drops_it(ast, field, path):
    assert code_for(ast, strict="content") is None


@pytest.mark.parametrize("ast, field, path", PRESENTATION)
def test_exact_refuses_presentation_by_name(ast, field, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict="exact")

    err = excinfo.value
    assert err.code == "unrepresentable"
    assert err.field == field
    assert err.path == path
    assert "cannot be expressed in markdown" in str(err)


def test_a_stock_tiptap_document_converts_under_content():
    # Issue #5, verbatim: StarterKit + Image + Link, a link with only href set. Node.toJSON()
    # serializes the computed attrs including defaults, so target/rel/class ride along on
    # every link whether or not the author touched them.
    stock = doc(
        p(
            {
                "type": "text",
                "text": "a",
                "marks": [
                    {
                        "type": "link",
                        "attrs": {
                            "href": "https://example.com",
                            "target": "_blank",
                            "rel": "noopener noreferrer nofollow",
                            "class": None,
                            "title": None,
                        },
                    }
                ],
            }
        ),
        p(
            {
                "type": "image",
                "attrs": {
                    "src": "https://example.com/x.png",
                    "alt": None,
                    "title": None,
                    "width": None,
                    "height": None,
                },
            }
        ),
        {
            "type": "orderedList",
            "attrs": {"start": 1, "type": None},
            "content": [{"type": "listItem", "content": [p(text("x"))]}],
        },
    )
    expected = "[a](https://example.com)\n\n![](https://example.com/x.png)\n\n1. x"

    assert tm.from_dict(stock, strict="content").to_markdown() == expected
    assert tm.from_dict(stock).to_markdown() == expected
    assert code_for(stock, strict="exact") == "unrepresentable"


@pytest.mark.parametrize(
    "ast, expected",
    [
        (image(src="a.png", width=[1, 2]), "invalid_attr_value"),
        (image(src="a.png", width=300), None),
        (image(src="a.png", width="300"), None),
        (image(src="a.png", width=True), "invalid_attr_value"),  # a width is not a bool
        (link(href="https://a", target=123), "invalid_attr_value"),
        (cell(colwidth=[100]), None),
        (cell(colwidth="100"), "invalid_attr_value"),
        (cell(colwidth=[1.5]), "invalid_attr_value"),
    ],
)
def test_content_still_type_checks_what_it_drops(ast, expected):
    # Dropped is not unchecked: a width of [1, 2] is a bug in the caller either way,
    # and saying so costs nothing since the value was never going to reach the markdown.
    assert code_for(ast, strict="content") == expected


def test_exact_refuses_a_dropped_attr_before_reading_its_value():
    # The name settles it at exact, so the caller is not told about a malformed width
    # they were never going to be allowed to keep.
    assert code_for(image(src="a.png", width=[1, 2]), strict="exact") == "unrepresentable"


# ── missing_attr: a destination that was never supplied ──────────────────────


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("attrs", [{"href": None}, {}, {"title": "t"}])
def test_a_link_with_no_destination_is_refused(attrs, level):
    # Issue #7. The three spellings of "this link has no destination" are one case:
    # absent, null, and no attrs dict at all. Writing "[a]()" for any of them is not a
    # lossy conversion but an invented one — it reads back as a real link node.
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(link(**attrs), strict=level)

    err = excinfo.value
    assert err.code == "missing_attr"
    assert err.field == "href"
    assert err.path == LINK_PATH
    assert str(err) == "attr 'href' is required for mark type 'link'"


@pytest.mark.parametrize("level", LEVELS)
def test_a_mark_or_node_with_no_attrs_key_at_all_is_the_same_case(level):
    # The check runs outside the `attrs` block for exactly this: there is no dict to walk.
    bare_link = doc(p({"type": "text", "text": "x", "marks": [{"type": "link"}]}))
    bare_image = doc(p({"type": "image"}))

    assert code_for(bare_link, strict=level) == "missing_attr"
    assert code_for(bare_image, strict=level) == "missing_attr"


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("attrs", [{"src": None}, {}, {"alt": "a"}])
def test_an_image_with_no_source_is_refused(attrs, level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(image(**attrs), strict=level)

    err = excinfo.value
    assert err.code == "missing_attr"
    assert err.field == "src"
    assert err.path == IMAGE_PATH


@pytest.mark.parametrize("level", LEVELS)
def test_an_empty_destination_is_supplied_not_missing(level):
    # "" is what the parser itself emits for "[a]()", and it round-trips exactly, so strict
    # has nothing to refuse. Rejecting an empty destination is the URI policy's job.
    assert tm.from_dict(link(href=""), strict=level).to_markdown() == "[x]()"
    assert code_for(image(src=""), strict=level) is None
    assert code_for(link(href=""), strict=level, link_relative="reject") == "disallowed_relative_url"


@pytest.mark.parametrize("level", LEVELS)
def test_a_missing_destination_is_reported_before_the_uri_policy(level):
    # Both would fire; the missing attr is the more specific answer, and it is the one a
    # caller can act on. The walk reaches it first, which is what makes that deterministic.
    assert code_for(link(href=None), strict=level, link_relative="reject") == "missing_attr"


def test_a_missing_destination_is_still_converted_when_strict_is_off():
    assert tm.from_dict(link()).to_markdown() == "[x]()"
    assert tm.from_dict(image()).to_markdown() == "![]()"


# ── None: an attr Tiptap serialized but never set ────────────────────────────


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "ast",
    [
        code_block(language=None),
        code_block(info=None),
        image(src="a.png", alt=None, title=None),
        link(href="https://a", title=None),
        doc({"type": "table", "attrs": {"colCount": None}}),
        cell(colwidth=None),
    ],
)
def test_none_on_an_optional_attr_is_unset_not_a_wrong_type(ast, level):
    # Issue #4. ProseMirror serializes every attr in the schema, defaults included,
    # and Tiptap declares `default: null` for each of these,
    # so this is what the editor submits for an attr nobody ever filled in.
    assert code_for(ast, strict=level) is None


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "with_null, without",
    [
        (code_block(language=None), code_block()),
        (image(src="a.png", alt=None, title=None), image(src="a.png")),
        (link(href="https://a", title=None), link(href="https://a")),
        (doc({"type": "table", "attrs": {"colCount": None}}), doc({"type": "table"})),
    ],
)
def test_a_null_attr_converts_exactly_like_an_absent_one(with_null, without, level):
    # Why accepting it is not a loosening:
    # strict admits no markdown here it was not already admitting from the absent-key form.
    assert tm.from_dict(with_null, strict=level).to_markdown() == tm.from_dict(without, strict=level).to_markdown()


@pytest.mark.parametrize("level", LEVELS)
def test_a_null_required_attr_fails_exactly_like_an_absent_one(level):
    # The same equivalence, in the direction where both sides are refused (#7).
    assert code_for(link(href=None), strict=level) == code_for(link(), strict=level) == "missing_attr"


def test_a_null_attr_is_dropped_rather_than_coerced():
    # from_dict keeps str, int and bool and drops every other value, so a null never
    # becomes a "" that to_dict() then hands back as if the caller had written it.
    assert "attrs" not in tm.from_dict(code_block(language=None)).to_dict()["content"][0]
    assert tm.from_dict(code_block(language=None, info="")).to_dict()["content"][0]["attrs"] == {"info": ""}


def test_a_value_markdown_cannot_carry_is_dropped_rather_than_stringified():
    # It used to arrive as "[100]" — a string the caller never wrote, standing in for a
    # value that was lost anyway.
    stored = tm.from_dict(cell(colwidth=[100], align="left")).to_dict()
    assert stored["content"][0]["content"][0]["content"][0]["attrs"] == {"align": "left"}


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "ast, field",
    [
        (doc(node("heading", level=None)), "level"),
        (ordered(start=None), "start"),
        (doc({"type": "taskList", "attrs": {"tight": None}}), "tight"),
        (doc(node("taskItem", checked=None)), "checked"),
        (cell(colspan=None), "colspan"),
    ],
)
def test_none_stays_wrong_where_tiptap_declares_a_non_null_default(ast, field, level):
    # These are settings rather than optional values. Tiptap gives every one a non-null
    # default, so it never emits a null here and one means the caller built the dict wrong.
    # The conversion would survive it; strict reports it because it is a bug, not a loss.
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)

    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == field


@pytest.mark.parametrize("level", LEVELS)
def test_a_null_html_attr_is_unset_and_still_reported(level):
    # htmlBlock/htmlInline are marktip's own node types, declared by no Tiptap schema, so a
    # null there is a caller mistake. It no longer erases the content — the key is dropped
    # and the child text is the payload, exactly as when the attr is absent.
    nulled = doc({"type": "htmlBlock", "attrs": {"html": None}, "content": [text("<div>hi</div>")]})
    absent = doc({"type": "htmlBlock", "content": [text("<div>hi</div>")]})

    assert tm.from_dict(nulled).to_markdown() == tm.from_dict(absent).to_markdown() == "<div>hi</div>"
    assert code_for(nulled, strict=level) == "invalid_attr_value"


def test_a_null_alt_falls_back_to_the_child_text_like_an_absent_one():
    # An alt of "" is the caption, an unset alt is not, and a null lands on the second.
    assert tm.from_dict(captioned_image(src="a.png", alt=None)).to_markdown() == "![cap](a.png)"
    assert tm.from_dict(captioned_image(src="a.png")).to_markdown() == "![cap](a.png)"
    assert tm.from_dict(captioned_image(src="a.png", alt="")).to_markdown() == "![](a.png)"


# ── accepted at every level: the structure already carries it ────────────────


@pytest.mark.parametrize("level", LEVELS)
def test_col_count_and_body_row_align_are_accepted_though_unused(level):
    # The serializer derives the column count from the rows and reads align only from the
    # header row, so neither attr is read — but neither is lost either, because the
    # structure it was describing survives. from_markdown emits both, which is why
    # refusing them would break re-parsing stored markdown; see the invariant below.
    assert code_for(doc({"type": "table", "attrs": {"colCount": 2}}), strict=level) is None
    body = doc(
        {
            "type": "table",
            "content": [
                {"type": "tableRow", "content": [node("tableHeader", align="left")]},
                {"type": "tableRow", "content": [node("tableCell", align="right")]},
            ],
        }
    )
    assert code_for(body, strict=level) is None


@pytest.mark.parametrize("level", LEVELS)
def test_col_count_is_still_an_int(level):
    assert code_for(doc({"type": "table", "attrs": {"colCount": -1}}), strict=level) == "invalid_attr_value"
    assert code_for(doc({"type": "table", "attrs": {"colCount": "2"}}), strict=level) == "invalid_attr_value"


# ── the invariant that keeps the exceptions above honest ─────────────────────


PARSER_CORPUS = [
    "# h1\n\n## h2\n\ntext with **bold**, *em*, `code` and ~~strike~~\n",
    "*outer _inner_ outer*\n",
    "**outer __inner__ outer**\n",
    "~~outer ~~inner~~ outer~~\n",
    "| a | b | c |\n| :-- | :-: | --: |\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n",
    "- a\n- b\n  - nested\n\n1. one\n2. two\n\n5. five\n",
    "- [ ] todo\n- [x] done\n",
    "> quote\n>\n> > nested\n",
    "```py\nprint(1)\n```\n\n~~~py`x\ninfo string with a backtick\n~~~\n",
    '[link](https://a.example "t") and ![img](i.png "cap")\n',
    "[empty]() and ![]()\n",
    "<div>raw</div>\n\ntext <span>inline</span> more\n",
    "---\n\npara with  \nhard break\n",
    "999999998. a\n999999999. b\n",
]


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("markdown", PARSER_CORPUS)
def test_strict_accepts_what_the_parser_produces(markdown, level):
    # A consumer that stores canonical markdown re-parses it on the read path (issue #1).
    # If strict rejected marktip's own output, that path would break on rows that were
    # written successfully — the failure mode that is hardest to notice.
    parsed = tm.from_markdown(markdown)
    assert tm.from_dict(parsed.to_dict(), strict=level).to_markdown() == parsed.to_markdown()


# ── surface ──────────────────────────────────────────────────────────────────


def test_strict_is_keyword_only():
    with pytest.raises(TypeError):
        tm.from_dict(doc(p(text())), "off")


def test_strict_takes_a_level_name_and_nothing_else():
    # Spelled like link_relative: a bad option value is a caller bug rather than a
    # malformed document, so it raises TypeError/ValueError instead of a MarktipError.
    with pytest.raises(TypeError, match="strict must be a str"):
        tm.from_dict(doc(p(text())), strict=True)
    with pytest.raises(ValueError, match="'off', 'content' or 'exact'"):
        tm.from_dict(doc(p(text())), strict="strict")


def test_strict_composes_with_the_uri_policy():
    ast = link(href="javascript:alert(1)", target="_blank")
    assert code_for(ast, link_schemes=("https",)) == "disallowed_scheme"
    assert code_for(ast, strict="exact") == "unrepresentable"
    assert code_for(ast, strict="content", link_schemes=("https",)) == "disallowed_scheme"


def test_every_violation_is_a_marktip_error():
    for ast in [cell(foo="bar"), cell(colspan=2), doc(node("heading", level=9)), link(), image(width=1)]:
        with pytest.raises(tm.MarktipError):
            tm.from_dict(ast, strict="content")
