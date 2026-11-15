"""Declared marks validate dict input and write their tag form."""

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
STRICT_LEVELS = ("content", "exact")
MARK_PATH = "content[0].content[0].marks[0]"
SECOND_MARK_PATH = "content[0].content[0].marks[1]"


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x", *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def mark(type_, **attrs):
    out = {"type": type_}
    if attrs:
        out["attrs"] = attrs
    return out


def marked(*marks):
    return doc(p(text("x", *marks)))


def stored_marks(document):
    return document.to_dict()["content"][0]["content"][0]["marks"]


def underline_schema():
    return tm.Schema(marks=[tm.MarkSpec("underline", tag="u")])


@pytest.mark.parametrize("level", LEVELS)
def test_declared_mark_writes_its_tag_and_document_keeps_the_schema(level):
    document = tm.from_dict(marked(mark("underline")), schema=underline_schema(), strict=level)
    assert stored_marks(document) == [mark("underline")]
    assert document.to_markdown(canonical=True) == "<u>x</u>"


def test_an_undeclared_mark_is_still_unknown():
    with pytest.raises(tm.UnknownTypeError) as excinfo:
        tm.from_dict(marked(mark("underline")))
    assert excinfo.value.code == "unknown_mark_type"
    assert excinfo.value.path == MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("attr, value", [
    (tm.Attr(str), 1),
    (tm.Attr(str), True),
    (tm.Attr(str), []),
    (tm.Attr(int), True),
    (tm.Attr(int), False),
    (tm.Attr(int), "1"),
    (tm.Attr(int), 1.0),
    (tm.Attr(int), 10**100),
    (tm.Attr(int), -(10**100)),
    (tm.Attr(bool), 0),
    (tm.Attr(bool), 1),
    (tm.Attr(bool), "true"),
    (tm.Attr(str, choices=("red", "blue")), "green"),
    (tm.Attr(int, choices=(1, 2)), 3),
    (tm.Attr(bool, choices=(True,)), False),
])
def test_declared_attr_rules_report_the_mark_location(level, attr, value):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": attr})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("note", value=value)), schema=schema, strict=level)
    err = excinfo.value
    assert err.code == "invalid_attr_value"
    assert err.field == "value"
    assert err.path == MARK_PATH
    assert err.detail == str(err)


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_, value, rendered", [
    (str, "", ""),
    (str, "café ' 한", "café ' 한"),
    (int, -(2**63), str(-(2**63))),
    (int, 2**63 - 1, str(2**63 - 1)),
    (int, 0, "0"),
    (bool, False, "false"),
    (bool, True, "true"),
])
def test_valid_declared_attr_values_are_carried_at_every_level(level, type_, value, rendered):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(type_)})])
    document = tm.from_dict(marked(mark("note", value=value)), schema=schema, strict=level)
    assert stored_marks(document) == [mark("note", value=value)]
    assert document.to_markdown(canonical=True) == f'<note value="{rendered}">x</note>'


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_unknown_attrs_and_mark_fields_keep_existing_error_shapes(level):
    schema = underline_schema()
    with pytest.raises(tm.InvalidNodeError) as attr_error:
        tm.from_dict(marked(mark("underline", typo="x")), schema=schema, strict=level)
    assert attr_error.value.code == "unknown_attr"
    assert attr_error.value.field == "typo"
    assert attr_error.value.path == MARK_PATH
    with pytest.raises(tm.InvalidNodeError) as field_error:
        tm.from_dict(marked({"type": "underline", "priority": 1}), schema=schema, strict=level)
    assert field_error.value.code == "unknown_field"
    assert field_error.value.field == "priority"
    assert field_error.value.path == MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("attrs", [{}, {"id": None}])
def test_required_attrs_refuse_missing_and_unset_values(level, attrs):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str, required=True)})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("comment", **attrs)), schema=schema, strict=level)
    assert excinfo.value.code == "missing_attr"
    assert excinfo.value.field == "id"
    assert excinfo.value.path == MARK_PATH


def test_off_skips_declared_attr_and_mark_set_validation():
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"id": tm.Attr(int, required=True)})])
    ast = marked(mark("note", id=True, unknown="lost"), mark("note"))
    document = tm.from_dict(ast, schema=schema, strict="off")
    assert stored_marks(document) == ast["content"][0]["content"][0]["marks"]
    assert document.to_markdown(canonical=True) == '<note id="true"><note>x</note></note>'


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_, default", [(str, "red"), (int, 0), (bool, False)])
def test_none_and_default_values_are_elided_at_every_level(level, type_, default):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(type_, default=default)})])
    for value in (None, default):
        document = tm.from_dict(marked(mark("note", value=value)), schema=schema, strict=level)
        assert stored_marks(document) == [mark("note")]
        assert document.to_markdown(canonical=True) == "<note>x</note>"


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_", [str, int, bool])
def test_none_is_unset_without_a_declared_default(level, type_):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(type_)})])
    document = tm.from_dict(marked(mark("note", value=None)), schema=schema, strict=level)
    assert stored_marks(document) == [mark("note")]


@pytest.mark.parametrize("type_, default, value", [(int, 0, False), (bool, False, 0)])
def test_default_comparison_distinguishes_bool_from_int(type_, default, value):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(type_, default=default)})])
    assert stored_marks(tm.from_dict(marked(mark("note", value=value)), schema=schema, strict="off")) == [
        mark("note", value=value)
    ]
    for level in STRICT_LEVELS:
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(marked(mark("note", value=value)), schema=schema, strict=level)
        assert excinfo.value.code == "invalid_attr_value"


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_default_self_exclusion_rejects_even_different_attrs(level):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"id": tm.Attr(str)})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("note", id="1"), mark("note", id="2")), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.field == "marks"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("second", [mark("comment", a="1", b="2"), mark("comment", b="2", a="1")])
def test_nonexclusive_marks_still_reject_equal_attr_sets(level, second):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"a": tm.Attr(str), "b": tm.Attr(str)}, excludes=())])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("comment", a="1", b="2"), second), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.field == "marks"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_mark_duplicates_are_compared_after_default_elision(level):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"tone": tm.Attr(str, default="red")}, excludes=())])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("comment", tone="red"), mark("comment")), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("other", ["note", "bold"])
def test_exclusions_are_symmetric_even_when_only_one_mark_names_the_other(level, reverse, other):
    declarations = [tm.MarkSpec("exclusive", excludes=(other,))]
    if other == "note":
        declarations.append(tm.MarkSpec("note", excludes=()))
    schema = tm.Schema(marks=declarations)
    marks = [mark("exclusive"), mark(other)]
    if reverse:
        marks.reverse()
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(*marks), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.field == "marks"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("other", ["bold", "code", "link"])
def test_wildcard_exclusion_includes_every_core_mark(level, reverse, other):
    schema = tm.Schema(marks=[tm.MarkSpec("exclusive", excludes="_")])
    other_mark = mark(other, href="https://example.com") if other == "link" else mark(other)
    marks = [mark("exclusive"), other_mark]
    if reverse:
        marks.reverse()
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(*marks), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_attr_validation_still_precedes_the_mark_set_conflict(level):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str, required=True)})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("comment", id="1"), mark("comment")), schema=schema, strict=level)
    assert excinfo.value.code == "missing_attr"
    assert excinfo.value.field == "id"
    assert excinfo.value.path == SECOND_MARK_PATH


@pytest.mark.parametrize("level", LEVELS)
def test_mark_order_is_core_input_order_then_declared_order_and_same_type_input_order(level):
    schema = tm.Schema(marks=[
        tm.MarkSpec("zulu"), tm.MarkSpec("alpha"),
        tm.MarkSpec("comment", attrs={"id": tm.Attr(str)}, excludes=()),
    ])
    document = tm.from_dict(marked(
        mark("alpha"), mark("italic"), mark("zulu"), mark("bold"), mark("comment", id="2"),
        mark("link", href="https://example.com"), mark("comment", id="1"),
    ), schema=schema, strict=level)
    assert stored_marks(document) == [
        mark("italic"), mark("bold"), mark("link", href="https://example.com"),
        mark("zulu"), mark("alpha"), mark("comment", id="2"), mark("comment", id="1"),
    ]


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", ["link", "image"])
def test_declared_uri_attrs_use_the_matching_scheme_policy(level, kind):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri=kind)})])
    options = {"link_schemes": ("https",), "image_schemes": ("http",)}
    ast = marked(mark("reference", url="http://example.com/x"))
    if kind == "image":
        document = tm.from_dict(ast, schema=schema, strict=level, **options)
        assert stored_marks(document) == [mark("reference", url="http://example.com/x")]
    else:
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(ast, schema=schema, strict=level, **options)
        assert excinfo.value.code == "disallowed_scheme"
        assert excinfo.value.field == "url"
        assert excinfo.value.path == MARK_PATH


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", ["link", "image"])
@pytest.mark.parametrize("value", ["https://a\0b", "https://a\tb", "https://a\nb", "https://a\x1fb", "https://a\x7fb"])
def test_uri_control_characters_are_rejected_without_nul_replacement(level, kind, value):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri=kind)})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("reference", url=value)), schema=schema, strict=level)
    assert excinfo.value.code == "invalid_uri_char"
    assert excinfo.value.field == "url"
    assert excinfo.value.path == MARK_PATH


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", ["link", "image"])
def test_uri_relative_policy_and_entity_decoding_apply_to_declared_attrs(level, kind):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri=kind)})])
    for value, options, code in [
        ("/relative", {f"{kind}_relative": "reject"}, "disallowed_relative_url"),
        ("https&colon;//example.com", {f"{kind}_schemes": ("https",), f"{kind}_relative": "reject"},
         "disallowed_relative_url"),
        ("//evil.example/x", {f"{kind}_relative": "path_only"}, "disallowed_relative_url"),
        ("&#106;avascript:x", {f"{kind}_schemes": ("https",)}, "disallowed_scheme"),
        ("java&Tab;script:x", {}, "invalid_uri_char"),
    ]:
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(marked(mark("reference", url=value)), schema=schema, strict=level, **options)
        assert excinfo.value.code == code
        assert excinfo.value.field == "url"
        assert excinfo.value.path == MARK_PATH


@pytest.mark.parametrize("level", LEVELS)
def test_non_uri_declared_strings_keep_existing_nul_normalization(level):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(str)})])
    document = tm.from_dict(marked(mark("note", value="a\0b")), schema=schema, strict=level)
    assert stored_marks(document) == [mark("note", value="a\ufffdb")]
    assert document.to_markdown(canonical=True) == '<note value="a\ufffdb">x</note>'


@pytest.mark.parametrize("level", LEVELS)
def test_rejected_node_names_are_still_node_names_with_a_declared_mark_schema(level):
    schema = underline_schema()
    with pytest.raises(ValueError):
        tm.from_dict(marked(mark("underline")), schema=schema, strict=level, reject_node_types=("underline",))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(marked(mark("underline")), schema=schema, strict=level, reject_node_types=("paragraph",))
    assert excinfo.value.code == "disallowed_node_type"
    assert excinfo.value.field == "type"
    assert excinfo.value.path == "content[0]"


@pytest.mark.parametrize("level", LEVELS)
def test_tag_attrs_write_in_declaration_order_and_escape_every_carried_control(level):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(str), "count": tm.Attr(int)})])
    value = '&"<>|`' + "".join(chr(number) for number in range(1, 32))
    escaped = "&amp;&quot;&lt;&gt;&#124;&#96;" + "".join(f"&#{number};" for number in range(1, 32))
    document = tm.from_dict(marked(mark("note", count=-12, value=value)), schema=schema, strict=level)
    assert document.to_markdown(canonical=True) == f'<note value="{escaped}" count="-12">x</note>'


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("core, rendered", [
    (mark("bold"), "**x**"),
    (mark("italic"), "*x*"),
    (mark("strike"), "~~x~~"),
    (mark("code"), "`x`"),
    (mark("link", href="https://example.com"), "[x](https://example.com)"),
])
def test_tag_marks_stay_outside_each_core_mark_in_both_input_orders(level, reverse, core, rendered):
    marks = [mark("underline"), core]
    if reverse:
        marks.reverse()
    document = tm.from_dict(marked(*marks), schema=underline_schema(), strict=level)
    assert document.to_markdown(canonical=True) == f"<u>{rendered}</u>"


@pytest.mark.parametrize("level", LEVELS)
def test_code_stays_innermost_with_all_other_marks(level):
    document = tm.from_dict(marked(
        mark("underline"), mark("bold"), mark("italic"), mark("strike"),
        mark("code"), mark("link", href="https://example.com"),
    ), schema=underline_schema(), strict=level)
    assert document.to_markdown(canonical=True) == "<u>***~~[`x`](https://example.com)~~***</u>"


@pytest.mark.parametrize("level", LEVELS)
def test_tag_mark_nesting_follows_declaration_order(level):
    schema = tm.Schema(marks=[tm.MarkSpec("zulu"), tm.MarkSpec("alpha")])
    document = tm.from_dict(marked(mark("alpha"), mark("bold"), mark("zulu")), schema=schema, strict=level)
    assert document.to_markdown(canonical=True) == "<zulu><alpha>**x**</alpha></zulu>"


@pytest.mark.parametrize("level", LEVELS)
def test_shared_tag_marks_remain_open_across_run_boundaries(level):
    document = tm.from_dict(doc(p(
        text("a", mark("bold")),
        text("b", mark("bold"), mark("underline")),
        text("c", mark("underline")),
    )), schema=underline_schema(), strict=level)
    assert document.to_markdown(canonical=True) == "**a**<u>**b**c</u>"


@pytest.mark.parametrize("level", LEVELS)
def test_same_type_nonexclusive_marks_can_overlap(level):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str, required=True)}, excludes=())])
    first = mark("comment", id="1")
    second = mark("comment", id="2")
    document = tm.from_dict(doc(p(text("a", first), text("b", first, second), text("c", second))),
                            schema=schema, strict=level)
    assert document.to_markdown(canonical=True) == (
        '<comment id="1">a<comment id="2">b</comment></comment><comment id="2">c</comment>'
    )


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("emphasis, delimiter", [("bold", "**"), ("italic", "*"), ("strike", "~~")])
def test_expelled_emphasis_whitespace_keeps_its_tag_mark(level, emphasis, delimiter):
    document = tm.from_dict(doc(p(text("left"), text(" x ", mark(emphasis), mark("underline")), text("right"))),
                            schema=underline_schema(), strict=level)
    assert document.to_markdown(canonical=True) == f"left<u> {delimiter}x{delimiter} </u>right"


@pytest.mark.parametrize("level", LEVELS)
def test_tag_marks_write_inside_headings_table_cells_and_on_images(level):
    schema = tm.Schema(marks=[tm.MarkSpec("note", tag="mark", attrs={"value": tm.Attr(str)})])
    tagged = mark("note", value="a|b")
    ast = doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [text("title", tagged, mark("bold"))]},
        {"type": "table", "content": [{"type": "tableRow", "content": [
            {"type": "tableHeader", "content": [p(text("cell", tagged))]},
        ]}]},
        p({"type": "image", "attrs": {"src": "image.png", "alt": "alt"}, "marks": [tagged, mark("bold")]}),
    )
    assert tm.from_dict(ast, schema=schema, strict=level).to_markdown(canonical=True) == (
        '## <mark value="a&#124;b">**title**</mark>\n\n'
        '| <mark value="a&#124;b">cell</mark> |\n| --- |\n\n'
        '<mark value="a&#124;b">**![alt](image.png)**</mark>'
    )


@pytest.mark.parametrize("level", ("content", "exact"))
def test_core_attr_type_errors_precede_unneeded_python_value_conversion(level):
    ast = {"type": "doc", "content": [{"type": "heading", "attrs": {"level": "\ud800"}}]}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "level"
    assert excinfo.value.path == "content[0]"
    assert str(excinfo.value) == "attr 'level' must be an int between 1 and 6"

    ast = {"type": "doc", "content": [{"type": "image", "attrs": {"alt": "\ud800", "src": 1}}]}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, strict=level)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "src"
    assert excinfo.value.path == "content[0]"
    assert str(excinfo.value) == "attr 'src' must be a str"


@pytest.mark.parametrize("level", ("off", "content", "exact"))
def test_uri_error_paths_keep_input_mark_indices_before_ordering(level):
    schema = tm.Schema(marks=[
        tm.MarkSpec("first", attrs={"url": tm.Attr(str, uri="link")}),
        tm.MarkSpec("second"),
    ])
    for bad_mark in (
        {"type": "link", "attrs": {"href": "javascript:x"}},
        {"type": "first", "attrs": {"url": "javascript:x"}},
    ):
        ast = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "x", "marks": [{"type": "second"}, bad_mark]},
        ]}]}
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(ast, schema=schema, strict=level, link_schemes=("https",))
        assert excinfo.value.code == "disallowed_scheme"
        assert excinfo.value.field == ("href" if bad_mark["type"] == "link" else "url")
        assert excinfo.value.path == "content[0].content[0].marks[1]"

