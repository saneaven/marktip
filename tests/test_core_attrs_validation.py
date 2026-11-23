"""Core attr overlays use shared strict rules and the active tag boundary policies."""

import pytest

import marktip as tm


STRICT_LEVELS = ("content", "exact")
PARENT_PATH = "content[0]"
INLINE_PATH = "content[0].content[0]"
MARK_PATH = INLINE_PATH + ".marks[0]"


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x", *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def mark(type_, **attrs):
    return {"type": type_, "attrs": attrs}


def node(type_, *children, **attrs):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def assert_error(excinfo, code, field, path):
    error = excinfo.value
    assert (error.code, error.field, error.path) == (code, field, path)
    assert error.detail == str(error)


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("type_, attrs, overlay, field, path", [
    ("paragraph", {"textAlign": "middle"}, {"textAlign": tm.Attr(str, choices=("left", "right"))},
     "textAlign", PARENT_PATH),
    ("heading", {"level": 2, "textAlign": 1}, {"textAlign": tm.Attr(str)}, "textAlign", PARENT_PATH),
    ("image", {"src": "image.png", "width": "320"}, {"width": tm.Attr(int)}, "width", INLINE_PATH),
    ("image", {"src": "image.png", "width": True}, {"width": tm.Attr(int)}, "width", INLINE_PATH),
    ("link", {"href": "https://example.com", "target": "_parent"},
     {"target": tm.Attr(str, choices=("_blank", "_self"))}, "target", MARK_PATH),
])
def test_strict_overlay_attr_values_use_declared_rules_and_existing_locations(
    level, type_, attrs, overlay, field, path,
):
    schema = tm.Schema(core_attrs={type_: overlay})
    if type_ == "link":
        ast = doc(p(text("x", mark(type_, **attrs))))
    elif type_ == "image":
        ast = doc(p(node(type_, **attrs)))
    else:
        ast = doc(node(type_, text(), **attrs))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert_error(excinfo, "invalid_attr_value", field, path)


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_an_overlay_does_not_make_unknown_attrs_known(level):
    schema = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(node("paragraph", text(), typo="center")), schema=schema, strict=level)
    assert_error(excinfo, "unknown_attr", "typo", PARENT_PATH)


@pytest.mark.parametrize("type_, field, value", [("image", "width", "320"), ("image", "width", 320),
                                               ("link", "rel", "noopener")])
def test_undeclared_dropped_attrs_stay_dropped_in_core_tag_forms(type_, field, value):
    if type_ == "image":
        schema = tm.Schema(core_attrs={"image": {"caption": tm.Attr(str)}})
        ast = doc(p(node("image", src="image.png", alt="", width=value, caption="note")))
    else:
        schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}})
        ast = doc(p(text("x", mark("link", href="https://example.com", rel=value, target="_self"))))
    document = tm.from_dict(ast, schema=schema, strict="content")
    assert document.to_dict() == ast
    written = document.to_markdown(canonical=True)
    assert f" {field}=" not in written
    parsed = tm.from_markdown(written, schema=schema).to_dict()["content"][0]["content"][0]
    attrs = parsed["marks"][0]["attrs"] if type_ == "link" else parsed["attrs"]
    assert field not in attrs
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict="exact")
    assert_error(excinfo, "unrepresentable", field, MARK_PATH if type_ == "link" else INLINE_PATH)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("type_, overlay, markup, code, field", [
    ("paragraph", {"textAlign": tm.Attr(str)}, '<p typo="x">x</p>', "unknown_attr", "typo"),
    ("heading", {"textAlign": tm.Attr(str)}, '<h2 typo="x">x</h2>', "unknown_attr", "typo"),
    ("image", {"width": tm.Attr(int)}, '<img src="image.png" width="wide"/>', "invalid_attr_value", "width"),
    ("link", {"target": tm.Attr(str, choices=("_self",))},
     '<a href="https://example.com" target="_blank">x</a>', "invalid_attr_value", "target"),
])
def test_lifted_core_tag_attrs_use_the_shared_located_rules(html, type_, overlay, markup, code, field):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=tm.Schema(core_attrs={type_: overlay}), html=html)
    assert_error(excinfo, code, field, PARENT_PATH)


@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("type_, overlay, markup, field", [
    ("image", {"width": tm.Attr(int)}, '<img src="image.png" width="10" height="20"/>', "height"),
    ("link", {"target": tm.Attr(str)}, '<a href="https://example.com" target="_self" rel="noopener">x</a>', "rel"),
])
def test_active_core_tags_reject_undeclared_dropped_attrs(html, type_, overlay, markup, field):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=tm.Schema(core_attrs={type_: overlay}), html=html)
    assert_error(excinfo, "unknown_attr", field, PARENT_PATH)


@pytest.mark.parametrize("type_, markup", [
    ("paragraph", "<p>x"),
    ("heading", "before <h2>x</h2>"),
    ("image", "</img>"),
    ("link", "<a/>"),
])
def test_active_core_tags_must_have_their_declared_shape(type_, markup):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=tm.Schema(core_attrs={type_: {}}))
    assert_error(excinfo, "invalid_tag", "content", PARENT_PATH)


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("type_, tag", [("paragraph", "p"), ("heading", "h2"), ("image", "img"), ("link", "a")])
@pytest.mark.parametrize("html_type", ("htmlInline", "htmlBlock"))
def test_strict_raw_html_cannot_collide_with_an_active_core_tag(level, type_, tag, html_type):
    payload = f"<{tag}>"
    html_node = node(html_type, html=payload)
    ast = doc(p(html_node)) if html_type == "htmlInline" else doc(html_node)
    schema = tm.Schema(core_attrs={type_: {}})
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert_error(excinfo, "unrepresentable", "html", INLINE_PATH if html_type == "htmlInline" else PARENT_PATH)
    assert tm.from_dict(ast, schema=schema, strict="off").to_dict() == ast


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_a_tagged_heading_must_be_the_only_child_of_a_table_cell(level):
    child = node("heading", text("first"), level=2, textAlign="center")
    ast = doc(node("table", node("tableRow", node("tableHeader", child, p(text("second")))), colCount=1))
    schema = tm.Schema(core_attrs={"heading": {"textAlign": tm.Attr(str)}})

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert_error(excinfo, "unrepresentable", "content", "content[0].content[0].content[0].content[0]")


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("first_attrs, second_attrs, index", [
    ({}, {"textAlign": "right"}, 1),
    ({"textAlign": "center"}, {"textAlign": "right"}, 0),
    ({"textAlign": "center"}, {}, 0),
])
def test_pipe_cell_refuses_paragraph_joins_that_would_change_tag_attrs(level, first_attrs, second_attrs, index):
    first = node("paragraph", text("first"), **first_attrs)
    second = node("paragraph", text("second"), **second_attrs)
    ast = doc(node("table", node("tableRow", node("tableHeader", first, second)), colCount=1))
    schema = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert_error(excinfo, "unrepresentable", "content", f"content[0].content[0].content[0].content[{index}]")


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("separator", ("bulletList", "table"))
def test_pipe_cell_refuses_tag_attrs_on_paragraphs_joined_across_a_removed_block(level, separator):
    second = node("paragraph", text("b"), textAlign="center")
    cell = node("tableHeader", p(text("a")), node(separator), second)
    ast = doc(node("table", node("tableRow", cell)))
    schema = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str)}})

    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert_error(excinfo, "unrepresentable", "content", "content[0].content[0].content[0].content[2]")


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_pipe_cell_joins_paragraphs_with_unset_tag_attrs(level):
    first = node("paragraph", text("first"), textAlign=None)
    second = node("paragraph", text("second"), textAlign="center")
    ast = doc(node("table", node("tableRow", node("tableHeader", first, second)), colCount=1))
    schema = tm.Schema(core_attrs={"paragraph": {"textAlign": tm.Attr(str, default="center")}})

    parsed = tm.from_dict(ast, schema=schema, strict=level)
    canonical = "| first<br>second |\n| --- |"
    assert parsed.to_markdown(canonical=True) == canonical
    assert tm.from_markdown(canonical, schema=schema) == parsed


@pytest.mark.parametrize("boundary", ("dict", "markdown"))
@pytest.mark.parametrize("type_", ("link", "image"))
@pytest.mark.parametrize("tag_form", (False, True))
@pytest.mark.parametrize("value, policy, code", [
    ("https&colon;//example.com", {"schemes": ("https",), "relative": "reject"}, "disallowed_relative_url"),
    ("&#106;avascript:x", {"schemes": ("https",)}, "disallowed_scheme"),
    ("java&Tab;script:x", {}, "invalid_uri_char"),
])
def test_active_core_uri_attrs_check_stored_and_decoded_forms(boundary, type_, tag_form, value, policy, code):
    field = "href" if type_ == "link" else "src"
    extra = {"target": "_self"} if type_ == "link" else {"width": 320}
    if not tag_form:
        extra = {}
    overlay = {"target": tm.Attr(str)} if type_ == "link" else {"width": tm.Attr(int)}
    schema = tm.Schema(core_attrs={type_: overlay})
    options = {f"{type_}_{name}": setting for name, setting in policy.items()}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if boundary == "dict":
            attrs = {field: value, **extra}
            ast = doc(p(text("x", mark("link", **attrs)))) if type_ == "link" else doc(p(node("image", **attrs)))
            tm.from_dict(ast, schema=schema, **options)
        elif tag_form:
            encoded = value.replace("&", "&amp;")
            markup = (f'<a href="{encoded}" target="_self">x</a>' if type_ == "link" else
                      f'<img src="{encoded}" width="320"/>')
            tm.from_markdown(markup, schema=schema, **options)
        else:
            markup = f"[x]({value})" if type_ == "link" else f"![x]({value})"
            tm.from_markdown(markup, schema=schema, **options)
    assert_error(excinfo, code, field, MARK_PATH if type_ == "link" else INLINE_PATH)


@pytest.mark.parametrize("type_", ("link", "image"))
def test_core_tag_uri_entities_are_decoded_once_before_the_finished_document_policy(type_):
    schema = tm.Schema(core_attrs={type_: {}})
    options = {f"{type_}_schemes": ("https",), f"{type_}_relative": "reject"}
    if type_ == "link":
        markup = '<a href="https&colon;//example.com">x</a>'
        expected = doc(p(text("x", mark("link", href="https://example.com"))))
    else:
        markup = '<img src="https&colon;//example.com"/>'
        expected = doc(p(node("image", src="https://example.com", alt="")))
    assert tm.from_markdown(markup, schema=schema, **options).to_dict() == expected


@pytest.mark.parametrize("boundary", ("dict", "markdown"))
@pytest.mark.parametrize("type_, field, uri, path", [
    ("paragraph", "source", "link", PARENT_PATH),
    ("link", "data-url", "image", MARK_PATH),
])
def test_core_overlay_uri_attrs_use_their_declared_policy(boundary, type_, field, uri, path):
    schema = tm.Schema(core_attrs={type_: {field: tm.Attr(str, uri=uri)}})
    attrs = {field: "http://example.com"}
    options = {f"{uri}_schemes": ("https",)}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if boundary == "dict":
            ast = (doc(node("paragraph", text(), **attrs)) if type_ == "paragraph" else
                   doc(p(text("x", mark("link", href="https://example.com", **attrs)))))
            tm.from_dict(ast, schema=schema, strict="exact", **options)
        else:
            markup = (f'<p {field}="http://example.com">x</p>' if type_ == "paragraph" else
                      f'<a href="https://example.com" {field}="http://example.com">x</a>')
            tm.from_markdown(markup, schema=schema, **options)
    assert_error(excinfo, "disallowed_scheme", field, path)


def test_tag_link_ordering_runs_after_uri_errors_use_the_input_mark_indices():
    schema = tm.Schema(core_attrs={"link": {"target": tm.Attr(str)}})
    ast = doc(p(text("x", mark("link", href="http://example.com", target="_self"), {"type": "bold"})))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, link_schemes=("https",))
    assert_error(excinfo, "disallowed_scheme", "href", MARK_PATH)
