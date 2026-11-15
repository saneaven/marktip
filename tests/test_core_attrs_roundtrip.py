"""Activated core tag forms preserve attrs that Markdown cannot carry."""

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children, **attrs):
    result = {"type": "paragraph", "content": list(children)}
    if attrs:
        result["attrs"] = attrs
    return result


def text(value, *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def mark(type_, **attrs):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    return result


def node(type_, *children, attrs=None, marks=()):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    if marks:
        result["marks"] = list(marks)
    return result


def alignment_schema():
    return tm.Schema(
        core_attrs={
            "paragraph": {"textAlign": tm.Attr(str, choices=("left", "center", "right"), default="left")},
            "heading": {"textAlign": tm.Attr(str, choices=("left", "center", "right"), default="left")},
        },
        marks=[tm.MarkSpec("underline", tag="u")],
        nodes=[tm.NodeSpec("mention", kind="inline", attrs={"id": tm.Attr(str, required=True)})],
    )


def roundtrip(ast, schema, markdown, html, level, **options):
    source = tm.from_dict(ast, schema=schema, strict=level, **options)
    written = source.to_markdown(canonical=True)
    if markdown is not None:
        assert written == markdown
    parsed = tm.from_markdown(written, schema=schema, html=html, **options)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == written
    return parsed


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_, tag", [("paragraph", "p"), ("heading", "h2")])
@pytest.mark.parametrize("context", ("root", "quote", "list", "table"))
def test_alignment_tags_keep_marks_and_custom_inline_nodes_in_block_contexts(html, level, type_, tag, context):
    children = (text("x", mark("bold"), mark("underline")), node("mention", attrs={"id": "u1"}))
    attrs = {"textAlign": "center"}
    if type_ == "heading":
        attrs["level"] = 2
    child = node(type_, *children, attrs=attrs)
    written = f'<{tag} textAlign="center"><u>**x**</u><mention id="u1"/></{tag}>'
    if context == "root":
        ast, markdown = doc(child), written
    elif context == "quote":
        ast, markdown = doc(node("blockquote", child)), "> " + written
    elif context == "list":
        ast = doc(node("bulletList", node("listItem", child), attrs={"tight": True}))
        markdown = "- " + written
    else:
        ast = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
        markdown = f"| {written} |\n| --- |"
    roundtrip(ast, alignment_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("type_, markdown", [("paragraph", "x"), ("heading", "## x")])
def test_default_alignment_is_unset_and_keeps_the_markdown_form(html, level, type_, markdown):
    attrs = {"textAlign": "left"}
    if type_ == "heading":
        attrs["level"] = 2
    parsed = roundtrip(doc(node(type_, text("x"), attrs=attrs)), alignment_schema(), markdown, html, level)
    assert "textAlign" not in parsed.to_dict()["content"][0].get("attrs", {})


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("child", [p(), node("heading", text("a"), node("hardBreak"), text("b"), attrs={"level": 2}),
                                   node("heading", text("a\nb"), attrs={"level": 2})])
@pytest.mark.parametrize("context", ("root", "quote", "list", "table"))
def test_unset_core_overlays_keep_empty_paragraph_and_heading_normalizations(html, level, child, context):
    schema = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str)},
                                   "heading": {"textAlign": tm.Attr(str)}})
    if context == "root":
        ast = doc(child)
    elif context == "quote":
        ast = doc(node("blockquote", child))
    elif context == "list":
        ast = doc(node("bulletList", node("listItem", child), attrs={"tight": True}))
    else:
        ast = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
    baseline = tm.from_dict(ast, strict=level)
    document = tm.from_dict(ast, schema=schema, strict=level)
    assert document.to_dict() == baseline.to_dict()
    assert document.to_markdown(canonical=True) == baseline.to_markdown(canonical=True)
    parsed = tm.from_markdown(document.to_markdown(canonical=True), schema=schema, html=html)
    baseline_parsed = tm.from_markdown(baseline.to_markdown(canonical=True), html=html)
    assert parsed.to_dict() == baseline_parsed.to_dict()
    assert parsed.to_markdown(canonical=True) == baseline_parsed.to_markdown(canonical=True)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_empty_paragraph_with_a_set_overlay_uses_the_normal_tag_form(html, level):
    schema = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})
    roundtrip(doc(p(textAlign="center")), schema, '<p textAlign="center"></p>', html, level)


@pytest.mark.parametrize("html", HTML)
def test_handwritten_empty_paragraph_tag_uses_general_textblock_reading(html):
    schema = tm.Schema(core_attrs={"paragraph": {}})
    parsed = tm.from_markdown("<p></p>", schema=schema, html=html)
    assert parsed.to_dict() == doc(node("paragraph"))
    assert parsed.to_markdown(canonical=True) == tm.from_dict(doc(p())).to_markdown(canonical=True)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("children, written", [
    ((text("a"), node("hardBreak"), text("b")), '<h2 textAlign="center">a  \nb</h2>'),
    ((text("a\nb"),), '<h2 textAlign="center">a\nb</h2>'),
])
def test_heading_with_a_set_overlay_preserves_breaks_and_newlines(html, level, children, written):
    schema = tm.Schema(core_attrs={"heading": {"textAlign": tm.Attr(str)}})
    ast = doc(node("heading", *children, attrs={"level": 2, "textAlign": "center"}))
    roundtrip(ast, schema, written, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("marks, opening, closing", [
    ([], "", ""),
    ([mark("bold")], "**", "**"),
    ([mark("link", href="https://example.com"), mark("bold")], "[**", "**](https://example.com)"),
])
def test_image_dimensions_keep_the_image_inside_link_and_emphasis_marks(html, level, marks, opening, closing):
    schema = tm.Schema(core_attrs={"image": {"width": tm.Attr(int), "height": tm.Attr(int)}})
    image = node("image", attrs={"src": "image.png", "alt": "caption", "width": 320, "height": 200},
                 marks=marks)
    markdown = opening + '<img src="image.png" alt="caption" width="320" height="200"/>' + closing
    roundtrip(doc(p(image)), schema, markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_image_tag_attrs_use_markdown_order_then_overlay_declaration_order(html, level):
    schema = tm.Schema(core_attrs={"image": {"width": tm.Attr(int), "data-note": tm.Attr(str),
                                            "height": tm.Attr(int), "enabled": tm.Attr(bool)}})
    image = node("image", attrs={"enabled": True, "width": 320, "src": "image.png", "alt": "a&b",
                                 "height": 200, "title": "note", "data-note": '"<>|`'})
    markdown = ('<img src="image.png" alt="a&amp;b" title="note" width="320" '
                'data-note="&quot;&lt;&gt;&#124;&#96;" height="200" enabled="true"/>')
    roundtrip(doc(p(image)), schema, markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_link_tag_attrs_use_markdown_order_then_overlay_declaration_order(html, level):
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str), "data-note": tm.Attr(str), "rel": tm.Attr(str)}})
    link = mark("link", rel="noopener", title="note", target="_self",
                href="https://example.com", **{"data-note": "a&b"})
    markdown = ('<a href="https://example.com" title="note" target="_self" '
                'data-note="a&amp;b" rel="noopener">x</a>')
    roundtrip(doc(p(text("x", link))), schema, markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("value, escaped", [("https://e.com/docs", r"https\://e.com/docs"),
                                           ("www.example.com", r"www\.example.com"),
                                           ("support@example.com", r"support\@example.com")])
def test_tag_link_text_escapes_autolink_triggers_and_outside_text_keeps_its_bytes(html, value, escaped):
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}})
    link = mark("link", href="https://example.com", target="_self")
    ast = doc(p(text("before "), text(f"visit {value} today", link, mark("bold")), text(" after")))
    markdown = f'before <a href="https://example.com" target="_self">**visit {escaped} today**</a> after'
    parsed = roundtrip(ast, schema, markdown, html, "exact")
    assert parsed.to_dict()["content"][0]["content"][1]["marks"] == [mark("bold"), link]
    outside = doc(p(text(f"visit {value} today")))
    assert tm.from_dict(outside, schema=schema).to_markdown(canonical=True) == tm.from_dict(outside).to_markdown(canonical=True)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("value", ("Read more.", "v1.2: ok"))
def test_tag_link_text_keeps_punctuation_that_is_not_an_autolink_trigger(html, value):
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}})
    link = mark("link", href="https://example.com", target="_self")
    markdown = f'<a href="https://example.com" target="_self">{value}</a>'
    roundtrip(doc(p(text(value, link))), schema, markdown, html, "exact")


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("value", ("https://e.com/docs", "www.example.com", "support@example.com"))
def test_markdown_form_link_text_keeps_its_existing_bytes_when_tag_form_is_active(html, value):
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str, default="_blank")}})
    link = mark("link", href="https://example.com")
    ast = doc(p(text(f"visit {value} today", link)))
    baseline = tm.from_dict(ast, strict="exact").to_markdown(canonical=True)
    roundtrip(ast, schema, baseline, html, "exact")


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("target", ("_blank", "_self"))
@pytest.mark.parametrize("reverse", (False, True))
def test_link_target_selects_its_form_and_only_tag_links_normalize_core_mark_order(html, level, target, reverse):
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str, default="_blank")}})
    marks = [mark("bold"), mark("link", href="https://example.com", target=target)]
    if reverse:
        marks.reverse()
    ast = doc(p(text("x", *marks)))
    if target == "_self":
        expected_marks = [mark("bold"), mark("link", href="https://example.com", target="_self")]
        markdown = '<a href="https://example.com" target="_self">**x**</a>'
    else:
        expected_marks = [mark("bold"), mark("link", href="https://example.com")]
        markdown = "**[x](https://example.com)**"
        if reverse:
            expected_marks.reverse()
            markdown = "[**x**](https://example.com)"
    source = tm.from_dict(ast, schema=schema, strict=level)
    assert source.to_dict()["content"][0]["content"][0]["marks"] == expected_marks
    parsed = roundtrip(ast, schema, markdown, html, level)
    assert parsed.to_dict()["content"][0]["content"][0]["marks"] == expected_marks


@pytest.mark.parametrize("html", HTML)
def test_tag_link_and_declared_marks_can_overlap_across_runs(html):
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}},
                       marks=[tm.MarkSpec("underline", tag="u")])
    link = mark("link", href="https://example.com", target="_self")
    underline = mark("underline")
    ast = doc(p(text("a", link), text("b", link, underline, mark("bold")), text("c", underline)))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    assert source.to_dict()["content"][0]["content"][1]["marks"] == [mark("bold"), link, underline]
    roundtrip(ast, schema, None, html, "exact")


def test_tag_link_order_preserves_the_relative_order_of_the_other_core_marks():
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}},
                       marks=[tm.MarkSpec("underline", tag="u")])
    link = mark("link", href="https://example.com", target="_self")
    ast = doc(p(text("x", link, mark("strike"), mark("underline"), mark("bold"))))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    expected = [mark("strike"), mark("bold"), link, mark("underline")]
    assert source.to_dict()["content"][0]["content"][0]["marks"] == expected
    parsed = tm.from_markdown(source.to_markdown(canonical=True), schema=schema)
    assert parsed.to_dict() == source.to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("type_, markup, expected, written", [
    ("image", '<img src="image.png" title=""/>',
     doc(p(node("image", attrs={"src": "image.png", "alt": ""}))), "![](image.png)"),
    ("link", '<a href="https://example.com" title="">x</a>',
     doc(p(text("x", mark("link", href="https://example.com")))), "[x](https://example.com)"),
])
def test_core_tag_lift_applies_markdown_image_and_link_normalizations(html, type_, markup, expected, written):
    schema = tm.Schema(core_attrs={type_: {}})
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == written
    assert tm.from_markdown(written, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", range(1, 7))
def test_each_heading_tag_supplies_its_level_without_a_level_attribute(html, level):
    schema = alignment_schema()
    markup = f'<h{level} textAlign="right">x</h{level}>'
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == doc(node("heading", text("x"), attrs={"level": level, "textAlign": "right"}))
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_int_list_attr_roundtrips_on_a_declared_inline_node(html, level):
    schema = tm.Schema(nodes=[tm.NodeSpec("measure", kind="inline", attrs={"widths": tm.Attr(tm.IntList)})])
    roundtrip(doc(p(node("measure", attrs={"widths": [100, 200]}))), schema,
              '<measure widths="100,200"/>', html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup", [
    "<p>x</p>",
    "<h3>x</h3>",
    'before <img src="image.png"/> after',
    'before <a href="https://example.com">x</a> after',
])
def test_core_tags_keep_the_existing_raw_html_behavior_when_the_type_is_inactive(html, markup):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag="u")])
    baseline = tm.from_markdown(markup, html=html)
    parsed = tm.from_markdown(markup, schema=schema, html=html)
    assert parsed.to_dict() == baseline.to_dict()
    assert parsed.to_markdown(canonical=True) == baseline.to_markdown(canonical=True)
