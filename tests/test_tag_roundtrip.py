"""Declared marks read the tag form written by the serializer."""

import time

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)
PARENT_PATH = "content[0]"
MARK_PATH = "content[0].content[0].marks[0]"


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
    value = {"type": type_}
    if attrs:
        value["attrs"] = attrs
    return value


def underline_schema():
    return tm.Schema(marks=[tm.MarkSpec("underline", tag="u")])


def roundtrip(ast, schema, markdown, html, level, expected=None, **options):
    source = tm.from_dict(ast, schema=schema, strict=level, **options)
    assert source.to_markdown(canonical=True) == markdown
    parsed = tm.from_markdown(markdown, schema=schema, html=html, **options)
    assert parsed.to_dict() == (source.to_dict() if expected is None else expected)
    assert parsed.to_markdown(canonical=True) == markdown
    return parsed


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_, value, encoded", [
    (str, "", ""),
    (str, "café ' 한", "café ' 한"),
    (int, -(2**63), str(-(2**63))),
    (int, 2**63 - 1, str(2**63 - 1)),
    (int, 0, "0"),
    (bool, False, "false"),
    (bool, True, "true"),
])
def test_written_declared_attr_types_roundtrip(html, level, type_, value, encoded):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(type_)})])
    roundtrip(doc(p(text("x", mark("note", value=value)))), schema,
              f'<note value="{encoded}">x</note>', html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_written_attr_escaping_and_declaration_order_roundtrip(html, level):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(str), "count": tm.Attr(int)})])
    value = '&"<>|`' + "".join(chr(number) for number in range(1, 32))
    encoded = "&amp;&quot;&lt;&gt;&#124;&#96;" + "".join(f"&#{number};" for number in range(1, 32))
    roundtrip(doc(p(text("x", mark("note", count=-12, value=value)))), schema,
              f'<note value="{encoded}" count="-12">x</note>', html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("reverse", (False, True))
@pytest.mark.parametrize("core, rendered", [
    (mark("bold"), "**x**"),
    (mark("italic"), "*x*"),
    (mark("strike"), "~~x~~"),
    (mark("code"), "`x`"),
    (mark("link", href="https://example.com"), "[x](https://example.com)"),
])
def test_written_tag_outside_each_core_mark_roundtrips(html, level, reverse, core, rendered):
    marks = [mark("underline"), core]
    if reverse:
        marks.reverse()
    roundtrip(doc(p(text("x", *marks))), underline_schema(), f"<u>{rendered}</u>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_written_code_remains_innermost_while_tag_marks_roundtrip(html, level):
    core = "***~~[`x`](https://example.com)~~***"
    expected = tm.from_markdown(core).to_dict()
    expected["content"][0]["content"][0]["marks"].append(mark("underline"))
    ast = doc(p(text("x", mark("underline"), mark("bold"), mark("italic"), mark("strike"),
                          mark("code"), mark("link", href="https://example.com"))))
    roundtrip(ast, underline_schema(), f"<u>{core}</u>", html, level, expected)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_written_tag_order_and_shared_runs_roundtrip(html, level):
    schema = tm.Schema(marks=[tm.MarkSpec("zulu"), tm.MarkSpec("alpha")])
    roundtrip(doc(p(text("x", mark("alpha"), mark("bold"), mark("zulu")))), schema,
              "<zulu><alpha>**x**</alpha></zulu>", html, level)
    ast = doc(p(text("a", mark("bold")), text("b", mark("bold"), mark("underline")),
                text("c", mark("underline"))))
    roundtrip(ast, underline_schema(), "**a**<u>**b**c</u>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_written_nonexclusive_same_type_overlap_roundtrips(html, level):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str, required=True)}, excludes=())])
    first = mark("comment", id="1")
    second = mark("comment", id="2")
    ast = doc(p(text("a", first), text("b", first, second), text("c", second)))
    markdown = '<comment id="1">a<comment id="2">b</comment></comment><comment id="2">c</comment>'
    roundtrip(ast, schema, markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("emphasis, delimiter", (("bold", "**"), ("italic", "*"), ("strike", "~~")))
def test_written_boundary_whitespace_retains_tag_marks(html, level, emphasis, delimiter):
    tag = mark("underline")
    core = mark(emphasis)
    ast = doc(p(text("left"), text(" x ", core, tag), text("right")))
    expected = doc(p(text("left"), text(" ", tag), text("x", core, tag), text(" ", tag), text("right")))
    roundtrip(ast, underline_schema(), f"left<u> {delimiter}x{delimiter} </u>right", html, level, expected)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_written_tags_roundtrip_in_headings_cells_and_images(html, level):
    schema = tm.Schema(marks=[tm.MarkSpec("note", tag="mark", attrs={"value": tm.Attr(str)})])
    tagged = mark("note", value="a|b")
    ast = doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [text("title", tagged, mark("bold"))]},
        {"type": "table", "attrs": {"colCount": 1}, "content": [{"type": "tableRow", "content": [
            {"type": "tableHeader", "content": [p(text("cell", tagged))]},
        ]}]},
        p({"type": "image", "attrs": {"src": "image.png", "alt": "alt"}, "marks": [tagged, mark("bold")]}),
    )
    markdown = ('## <mark value="a&#124;b">**title**</mark>\n\n'
                '| <mark value="a&#124;b">cell</mark> |\n| --- |\n\n'
                '<mark value="a&#124;b">**![alt](image.png)**</mark>')
    roundtrip(ast, schema, markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("context", ("quote", "tight", "loose", "task", "ordered_task"))
def test_written_tags_roundtrip_in_core_containers(html, level, context):
    blocks = [p(text("x", mark("underline")))]
    if context == "quote":
        ast = doc({"type": "blockquote", "content": blocks})
        markdown = "> <u>x</u>"
    elif context in ("tight", "loose"):
        items = [{"type": "listItem", "content": blocks}]
        markdown = "- <u>x</u>"
        if context == "loose":
            items.append({"type": "listItem", "content": [p(text("y", mark("underline")))]})
            markdown += "\n\n- <u>y</u>"
        ast = doc({"type": "bulletList", "attrs": {"tight": context == "tight"}, "content": items})
    else:
        item = {"type": "taskItem", "attrs": {"checked": True}, "content": blocks}
        if context == "task":
            ast = doc({"type": "taskList", "attrs": {"tight": True}, "content": [item]})
            markdown = "- [x] <u>x</u>"
        else:
            ast = doc({"type": "orderedList", "attrs": {"start": 1, "tight": True}, "content": [item]})
            markdown = "1. [x] <u>x</u>"
    roundtrip(ast, underline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_written_breaks_keep_their_tag_marks(html, level):
    tagged = mark("underline")
    ast = doc(p(text("a", tagged), {"type": "hardBreak", "marks": [tagged]}, text("b", tagged)))
    roundtrip(ast, underline_schema(), "<u>a  \nb</u>", html, level)
    ast = doc({"type": "table", "attrs": {"colCount": 1}, "content": [{"type": "tableRow", "content": [
        {"type": "tableHeader", "content": [p(text("a", tagged),
                                                {"type": "hardBreak", "marks": [tagged]}, text("b", tagged))]},
    ]}]})
    roundtrip(ast, underline_schema(), "| <u>a<br>b</u> |\n| --- |", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("type_, default, encoded", ((str, "red", "red"), (int, 0, "0"), (bool, False, "false")))
def test_reading_default_attrs_elides_instead_of_materializing_them(html, type_, default, encoded):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(type_, default=default)})])
    expected = doc(p(text("x", mark("note"))))
    assert tm.from_markdown(f'<note value="{encoded}">x</note>', schema=schema, html=html).to_dict() == expected
    parsed = tm.from_markdown("<note>x</note>", schema=schema, html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == "<note>x</note>"


@pytest.mark.parametrize("html", HTML)
def test_reader_accepts_quoted_unquoted_and_valueless_declared_attrs(html):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={
        "enabled": tm.Attr(bool), "count": tm.Attr(int), "label": tm.Attr(str),
    })])
    parsed = tm.from_markdown("<note label=red enabled count='-12'>x</note>", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("x", mark("note", enabled=True, count=-12, label="red"))))
    assert parsed.to_markdown(canonical=True) == '<note enabled="true" count="-12" label="red">x</note>'


@pytest.mark.parametrize("html", HTML)
def test_self_exclusive_nested_tags_replace_then_restore_the_outer_mark(html):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"color": tm.Attr(str)})])
    parsed = tm.from_markdown('<note color="red">a<note color="blue">b</note>c</note>', schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("a", mark("note", color="red")),
                                     text("b", mark("note", color="blue")), text("c", mark("note", color="red"))))
    assert parsed.to_markdown(canonical=True) == ('<note color="red">a</note><note color="blue">b</note>'
                                    '<note color="red">c</note>')
    folded = tm.from_markdown('<note color="red">a<note color="red">b</note>c</note>', schema=schema, html=html)
    assert folded.to_dict() == doc(p(text("abc", mark("note", color="red"))))


@pytest.mark.parametrize("html", HTML)
def test_declared_marks_may_cross_other_tag_and_core_mark_boundaries(html):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag="u"), tm.MarkSpec("note")])
    parsed = tm.from_markdown("<u>a<note>b</u>c</note>", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("a", mark("underline")),
                                     text("b", mark("underline"), mark("note")), text("c", mark("note"))))
    parsed = tm.from_markdown("**a <u>b** c</u>", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("a ", mark("bold")),
                                     text("b", mark("bold"), mark("underline")), text(" c", mark("underline"))))
    link = mark("link", href="https://example.com")
    parsed = tm.from_markdown("[a <u>b](https://example.com) c</u>", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("a ", link), text("b", link, mark("underline")),
                                     text(" c", mark("underline"))))
    parsed = tm.from_markdown("<u>[a</u> b](https://example.com)", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("a", link, mark("underline")), text(" b", link)))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markdown", ("<u></u>", "<u><u></u></u>"))
def test_empty_tag_marks_do_not_leave_a_mark(html, markdown):
    parsed = tm.from_markdown(markdown, schema=underline_schema(), html=html)
    assert parsed.to_markdown(canonical=True) == ""
    assert all("marks" not in node for block in parsed.to_dict()["content"] for node in block.get("content", []))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("outer", (False, True))
def test_empty_tag_marks_do_not_split_undeclared_html(html, outer):
    markup = "<span><u></u></span>"
    marks = (mark("underline"),) if outer else ()
    if outer:
        markup = "<u>" + markup + "</u>"
    if html:
        node = {"type": "htmlInline", "attrs": {"html": "<span></span>"}}
        if marks:
            node["marks"] = list(marks)
    else:
        node = text("<span></span>", *marks)
    parsed = tm.from_markdown(markup, schema=underline_schema(), html=html)
    assert parsed.to_dict() == doc(p(node))
    assert tm.from_markdown(parsed.to_markdown(canonical=True), schema=underline_schema(), html=html).to_dict() == parsed.to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markdown", ("<u>x", "x</u>", "<u>x\n\ny</u>"))
def test_unmatched_declared_tags_report_the_inline_parent(html, markdown):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=underline_schema(), html=html)
    assert excinfo.value.code == "invalid_tag"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("attr, markup, code", [
    (tm.Attr(str), '<note typo="x">x</note>', "unknown_attr"),
    (tm.Attr(str, required=True), "<note>x</note>", "missing_attr"),
    (tm.Attr(int), '<note value="true">x</note>', "invalid_attr_value"),
    (tm.Attr(int), '<note value="9223372036854775808">x</note>', "invalid_attr_value"),
    (tm.Attr(bool), '<note value="1">x</note>', "invalid_attr_value"),
    (tm.Attr(str, choices=("red", "blue")), '<note value="green">x</note>', "invalid_attr_value"),
])
def test_read_declared_attr_rules_use_existing_located_errors(html, attr, markup, code):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": attr})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema, html=html)
    assert excinfo.value.code == code
    assert excinfo.value.field == ("typo" if code == "unknown_attr" else "value")
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("reverse", (False, True))
@pytest.mark.parametrize("other", ("note", "bold"))
def test_excluded_read_mark_combinations_are_rejected_in_both_directions(html, reverse, other):
    declarations = [tm.MarkSpec("exclusive", excludes=(other,))]
    if other == "note":
        declarations.append(tm.MarkSpec("note", excludes=()))
    schema = tm.Schema(marks=declarations)
    markup = "<exclusive><note>x</note></exclusive>" if other == "note" else "<exclusive>**x**</exclusive>"
    if reverse:
        markup = "<note><exclusive>x</exclusive></note>" if other == "note" else "**<exclusive>x</exclusive>**"
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema, html=html)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.field == "marks"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
def test_equal_nonexclusive_read_marks_are_rejected_when_the_inner_tag_opens(html):
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str)}, excludes=())])
    for body in ("x", ""):
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_markdown(f'<comment id="1"><comment id="1">{body}</comment></comment>',
                             schema=schema, html=html)
        assert excinfo.value.code == "invalid_mark_set"
        assert excinfo.value.field == "marks"
        assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("kind", ("link", "image"))
def test_written_declared_uri_attrs_roundtrip_under_the_matching_policy(html, kind):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri=kind)})])
    options = {"link_schemes": ("https",), "image_schemes": ("http",)}
    value = ("https" if kind == "link" else "http") + "://example.com/a&b"
    ast = doc(p(text("x", mark("reference", url=value))))
    encoded = value.replace("&", "&amp;")
    roundtrip(ast, schema, f'<reference url="{encoded}">x</reference>', html, "exact", **options)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("kind", ("link", "image"))
@pytest.mark.parametrize("value, options, code", [
    ("https&colon;//example.com", {"schemes": ("https",), "relative": "reject"}, "disallowed_relative_url"),
    ("&#106;avascript:x", {"schemes": ("https",)}, "disallowed_scheme"),
    ("java&Tab;script:x", {}, "invalid_uri_char"),
])
def test_uri_policy_checks_the_value_carried_by_written_tags(html, kind, value, options, code):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri=kind)})])
    options = {f"{kind}_{name}": setting for name, setting in options.items()}
    encoded = value.replace("&", "&amp;")
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f'<reference url="{encoded}">x</reference>', schema=schema, html=html, **options)
    assert excinfo.value.code == code
    assert excinfo.value.field == "url"
    assert excinfo.value.path == MARK_PATH


@pytest.mark.parametrize("html", HTML)
def test_raw_tag_uri_entities_are_decoded_once_before_policy_checks(html):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri="link")})])
    parsed = tm.from_markdown('<reference url="https&colon;//example.com">x</reference>', schema=schema, html=html,
                              link_schemes=("https",), link_relative="reject")
    assert parsed.to_dict() == doc(p(text("x", mark("reference", url="https://example.com"))))


@pytest.mark.parametrize("html", HTML)
def test_post_build_node_policy_still_precedes_declared_uri_policy(html):
    schema = tm.Schema(marks=[tm.MarkSpec("reference", attrs={"url": tm.Attr(str, uri="link")})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown('<reference url="javascript:x">x</reference>', schema=schema, html=html,
                         reject_node_types=("paragraph",), link_schemes=("https",))
    assert excinfo.value.code == "disallowed_node_type"
    assert excinfo.value.field == "type"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
def test_declared_tag_carriers_are_no_longer_raw_html_nodes(html):
    parsed = tm.from_markdown("<u>x</u>", schema=underline_schema(), html=html,
                              reject_node_types=("htmlBlock", "htmlInline"))
    assert parsed.to_dict() == doc(p(text("x", mark("underline"))))


@pytest.mark.parametrize("html", HTML)
def test_unknown_html_stays_html_or_literal_text_beside_declared_tags(html):
    parsed = tm.from_markdown("<u>x</u><span>y</span>", schema=underline_schema(), html=html)
    if html:
        expected = doc(p(text("x", mark("underline")), {"type": "htmlInline", "attrs": {"html": "<span>"}},
                         text("y"), {"type": "htmlInline", "attrs": {"html": "</span>"}}))
    else:
        expected = doc(p(text("x", mark("underline")), text("<span>y</span>")))
    assert parsed.to_dict() == expected


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("type_, payload", [
    ("htmlInline", "<u>"),
    ("htmlInline", "</u>"),
    ("htmlInline", "<u>x</u>"),
    ("htmlInline", "prefix<u>x</u>tail"),
    ("htmlBlock", "<u>"),
    ("htmlBlock", "</u>"),
    ("htmlBlock", "<u>x</u>"),
])
def test_strict_dict_rejects_raw_html_that_the_schema_would_read_as_marks(level, type_, payload):
    node = {"type": type_, "attrs": {"html": payload}}
    ast = doc(p(node)) if type_ == "htmlInline" else doc(node)
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=underline_schema(), strict=level)
    assert excinfo.value.code == "unrepresentable"
    assert excinfo.value.field == "html"
    assert excinfo.value.path == ("content[0].content[0]" if type_ == "htmlInline" else PARENT_PATH)
    assert tm.from_dict(ast, schema=underline_schema(), strict="off").to_dict() == ast


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("payload", ("<!-- <u> -->", "<?x <u> ?>", "<![CDATA[<u>]]>", "<u-other>x</u-other>"))
def test_opaque_or_undeclared_html_remains_accepted_by_strict_dict(level, payload):
    ast = doc(p({"type": "htmlInline", "attrs": {"html": payload}}))
    assert tm.from_dict(ast, schema=underline_schema(), strict=level).to_dict() == ast


@pytest.mark.parametrize("level", ("content", "exact"))
def test_strict_does_not_check_that_html_block_payload_is_an_html_block_start(level):
    ast = doc({"type": "htmlBlock", "attrs": {"html": "prefix<u>x</u>tail"}})
    assert tm.from_dict(ast, schema=underline_schema(), strict=level).to_dict() == ast


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("attributes, field", [
    ('value="same" value="same"', "value"),
    ('value="first" value="second"', "value"),
    ("enabled enabled", "enabled"),
    ('enabled="true" enabled', "enabled"),
])
def test_repeated_declared_attrs_are_rejected_at_the_inline_parent(html, attributes, field):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"value": tm.Attr(str), "enabled": tm.Attr(bool)})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"<note {attributes}>x</note>", schema=schema, html=html)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == field
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup", ("<u/>", "<u />", '<note value="x"/>', '<note value="x" />'))
def test_declared_mark_tags_cannot_be_self_closing(html, markup):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag="u"), tm.MarkSpec("note", attrs={"value": tm.Attr(str)})])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema, html=html)
    assert excinfo.value.code == "invalid_tag"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("name", ("U", "u-other"))
def test_tag_names_match_exactly_with_no_case_or_prefix_match(html, name):
    markdown = f"before <{name}>x</{name}> after"
    expected = tm.from_markdown(markdown, html=html).to_dict()
    assert tm.from_markdown(markdown, schema=underline_schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markdown, expected", [
    (r"\<u>x\</u>", doc(p(text("<u>x</u>")))),
    ("&lt;u&gt;x&lt;/u&gt;", doc(p(text("<u>x</u>")))),
    ("`<u>x</u>`", doc(p(text("<u>x</u>", mark("code"))))),
    ("```\n<u>x</u>\n```", doc({"type": "codeBlock", "content": [text("<u>x</u>\n")]})),
])
def test_tag_shapes_in_escaped_text_entities_and_code_are_not_lifted(html, markdown, expected):
    assert tm.from_markdown(markdown, schema=underline_schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("construct", (
    "<!-- <u> -->",
    "<?test <u> ?>",
    "<![CDATA[<u>]]>",
    "<!DOCTYPE <u> >",
))
def test_opaque_html_constructs_do_not_open_their_embedded_tag(html, construct):
    markdown = f"before {construct} after"
    expected = tm.from_markdown(markdown, html=html).to_dict()
    assert tm.from_markdown(markdown, schema=underline_schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
def test_tag_shape_in_an_undeclared_quoted_attr_does_not_open_a_mark(html):
    markdown = 'before <span data-note="<u>">x</span> after'
    expected = tm.from_markdown(markdown, html=html).to_dict()
    assert tm.from_markdown(markdown, schema=underline_schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
def test_attr_order_variants_merge_adjacent_text_after_decoding(html):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"a": tm.Attr(str), "b": tm.Attr(int)})])
    markup = '<note a="x" b="1">a</note><note b="1" a="x">b</note>'
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("ab", mark("note", a="x", b=1))))
    assert parsed.to_markdown(canonical=True) == '<note a="x" b="1">ab</note>'


@pytest.mark.parametrize("html", HTML)
def test_declared_open_order_variants_merge_after_mark_ordering(html):
    schema = tm.Schema(marks=[tm.MarkSpec("first"), tm.MarkSpec("second")])
    markup = "<first><second>a</second></first><second><first>b</first></second>"
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("ab", mark("first"), mark("second"))))
    assert parsed.to_markdown(canonical=True) == "<first><second>ab</second></first>"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("literal, value", [
    ("0", 0),
    ("+0", 0),
    ("-0", 0),
    ("1", 1),
    ("+1", 1),
    ("-1", -1),
    ("001", 1),
    ("+001", 1),
    ("-001", -1),
    ("&#43;001", 1),
    ("&#45;001", -1),
    (str(-(2**63)), -(2**63)),
    (str(2**63 - 1), 2**63 - 1),
    ("+" + str(2**63 - 1), 2**63 - 1),
])
def test_declared_int_attrs_accept_the_entire_signed_decimal_value(html, literal, value):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"count": tm.Attr(int)})])
    parsed = tm.from_markdown(f'<note count="{literal}">x</note>', schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("x", mark("note", count=value))))
    assert parsed.to_markdown(canonical=True) == f'<note count="{value}">x</note>'


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("literal", (None, "", " ", " 1", "1 ", "\t1", "1&#32;", "1x", "1.0", "0x10",
                                      "+", "-", "+-1", "--1", "++1", str(2**63), str(-(2**63) - 1)))
def test_declared_int_attrs_reject_missing_digits_whitespace_partial_values_and_overflow(html, literal):
    schema = tm.Schema(marks=[tm.MarkSpec("note", attrs={"count": tm.Attr(int)})])
    attribute = "count" if literal is None else f'count="{literal}"'
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"<note {attribute}>x</note>", schema=schema, html=html)
    assert excinfo.value.code == "invalid_attr_value"
    assert excinfo.value.field == "count"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("schema", (1, {}, (), "schema"))
def test_from_markdown_rejects_a_wrong_schema_type(schema):
    with pytest.raises(TypeError):
        tm.from_markdown("x", schema=schema)


@pytest.mark.parametrize("html", HTML)
def test_from_markdown_rejected_node_types_cannot_name_a_declared_mark(html):
    with pytest.raises(ValueError):
        tm.from_markdown("<u>x</u>", schema=underline_schema(), html=html, reject_node_types=("underline",))


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("opening, closing", (("<!--", " -->"), ("<?", " ?>"), ("<![CDATA[", "]]>")))
@pytest.mark.parametrize("padding", ("", " ", "\t"))
def test_raw_inline_opaque_opener_ending_at_newline_does_not_hide_a_declared_tag(level, opening, closing, padding):
    payload = f"{opening}{padding}\n<u>x</u>{closing}"
    ast = doc(p({"type": "htmlInline", "attrs": {"html": payload}}))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=underline_schema(), strict=level)
    assert excinfo.value.code == "unrepresentable"
    assert excinfo.value.field == "html"
    assert excinfo.value.path == "content[0].content[0]"


@pytest.mark.parametrize("level", ("content", "exact"))
def test_raw_inline_opaque_opener_with_body_before_newline_keeps_its_contents_opaque(level):
    ast = doc(p({"type": "htmlInline", "attrs": {"html": "<!--x\n<u>x</u> -->"}}))
    assert tm.from_dict(ast, schema=underline_schema(), strict=level).to_dict() == ast


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("body", ("", "x"))
def test_excluded_declared_pair_is_rejected_even_when_the_inner_tag_is_empty(html, body):
    schema = tm.Schema(marks=[
        tm.MarkSpec("superscript", tag="sup", excludes=("subscript",)),
        tm.MarkSpec("subscript", tag="sub", excludes=()),
    ])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"<sup><sub></sub>{body}</sup>", schema=schema, html=html)
    assert excinfo.value.code == "invalid_mark_set"
    assert excinfo.value.field == "marks"
    assert excinfo.value.path == PARENT_PATH


def test_two_thousand_nonexclusive_nested_marks_parse_in_under_one_second():
    depth = 2000
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(int)}, excludes=())])
    markdown = "".join(f'<comment id="{index}">x' for index in range(depth)) + "</comment>" * depth
    start = time.perf_counter()
    parsed = tm.from_markdown(markdown, schema=schema)
    elapsed = time.perf_counter() - start
    assert isinstance(parsed, tm.Document)
    assert elapsed < 1.0, f"2000 nested nonexclusive marks took {elapsed:.3f}s"


def test_nonexclusive_mark_nesting_uses_the_existing_depth_limit():
    depth = 2048
    schema = tm.Schema(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(int)}, excludes=())])
    opening = "".join(f'<comment id="{index}">' for index in range(depth))
    closing = "</comment>" * depth
    parsed = tm.from_markdown(opening + "x" + closing, schema=schema)
    marks = parsed.to_dict()["content"][0]["content"][0]["marks"]
    assert len(marks) == depth

    with pytest.raises(tm.ParseError) as excinfo:
        tm.from_markdown(opening + f'<comment id="{depth}">x</comment>' + closing, schema=schema)
    assert excinfo.value.code == "markdown_max_depth"
    assert excinfo.value.path == ""


def assert_tag_boundary_whitespace_normalizes_once(emphasis, delimiter, html):
    schema = underline_schema()
    first = tm.from_markdown(f"{delimiter}a <u>b</u>{delimiter}", schema=schema, html=html)
    assert first.to_dict() == doc(p(text("a ", mark(emphasis)),
                                    text("b", mark(emphasis), mark("underline"))))
    normalized = f"{delimiter}a{delimiter} <u>{delimiter}b{delimiter}</u>"
    assert first.to_markdown(canonical=True) == normalized
    second = tm.from_markdown(normalized, schema=schema, html=html)
    assert second.to_dict() == doc(p(text("a", mark(emphasis)), text(" "),
                                     text("b", mark(emphasis), mark("underline"))))
    assert second.to_markdown(canonical=True) == normalized
    third = tm.from_markdown(second.to_markdown(canonical=True), schema=schema, html=html)
    assert third.to_dict() == second.to_dict()
    assert third.to_markdown(canonical=True) == normalized


@pytest.mark.parametrize("html", HTML)
def test_bold_whitespace_at_a_tag_boundary_normalizes_once(html):
    assert_tag_boundary_whitespace_normalizes_once("bold", "**", html)


@pytest.mark.parametrize("html", HTML)
def test_italic_whitespace_at_a_tag_boundary_normalizes_once(html):
    assert_tag_boundary_whitespace_normalizes_once("italic", "*", html)


@pytest.mark.parametrize("html", HTML)
def test_strike_whitespace_at_a_tag_boundary_normalizes_once(html):
    assert_tag_boundary_whitespace_normalizes_once("strike", "~~", html)


@pytest.mark.parametrize("html", HTML)
def test_self_closing_closer_names_the_actual_offending_tag(html):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("</u/>", schema=underline_schema(), html=html)
    assert excinfo.value.code == "invalid_tag"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == PARENT_PATH
    assert "</u/>" in str(excinfo.value)
