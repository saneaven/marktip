"""The schema can select the block shape of Tiptap's image node."""

import json

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)
MARKDOWN_IMAGE = '![Logo](/logo.png "A logo")'
TAG_IMAGE = '<img src="/logo.png" alt="Logo" title="A logo"/>'


def doc(*children):
    return {"type": "doc", "content": list(children)}


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
    return result


def p(*children):
    return node("paragraph", *children)


def text(value, *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def image(*, sized=False):
    attrs = {"src": "/logo.png", "alt": "Logo", "title": "A logo"}
    if sized:
        attrs.update(width=320, height=200)
    return node("image", attrs=attrs)


def schema(*, sized=False):
    return tm.Schema(block_image=True, core_attrs=tm.IMAGE_SIZE if sized else None)


def in_context(child, context):
    if context == "doc":
        return doc(child)
    if context == "quote":
        return doc(node("blockquote", child))
    if context == "bullet":
        return doc(node("bulletList", node("listItem", child), attrs={"tight": True}))
    if context == "ordered":
        return doc(node("orderedList", node("listItem", child), attrs={"start": 1, "tight": True}))
    if context == "task":
        return doc(node("taskList", node("taskItem", child, attrs={"checked": True}), attrs={"tight": True}))
    return doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))


def assert_error(excinfo, code, field, path=None):
    error = excinfo.value
    assert (error.code, error.field) == (code, field)
    if path is not None:
        assert error.path == path
    assert error.detail == str(error)


def test_block_image_option_is_part_of_schema_persistence_and_identity():
    baseline = tm.Schema()
    enabled = tm.Schema(block_image=True)
    assert baseline.block_image is False
    assert enabled.block_image is True
    assert "block_image" not in baseline.to_dict()
    assert enabled.to_dict() == {"marks": [], "block_image": True}
    assert tm.Schema.from_dict(json.loads(json.dumps(enabled.to_dict()))) == enabled
    assert tm.Schema.from_dict({"marks": [], "block_image": False}) == baseline
    assert enabled != baseline
    assert {enabled: "block", baseline: "inline"}[tm.Schema(block_image=True)] == "block"


def test_extend_inherits_the_image_shape_unless_it_is_explicitly_changed():
    base = tm.Schema(block_image=True, marks=[tm.UNDERLINE])
    inherited = base.extend(nodes=[tm.MENTION])
    assert inherited.block_image is True
    assert inherited.marks == base.marks
    assert inherited.nodes == (tm.MENTION,)
    inline = inherited.extend(block_image=False)
    assert inline.block_image is False
    assert "block_image" not in inline.to_dict()
    assert inline.extend(block_image=True) == inherited


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("context", ("doc", "quote", "bullet", "ordered", "task", "table"))
@pytest.mark.parametrize("sized", (False, True))
def test_block_images_roundtrip_in_their_block_parent_contexts(level, html, context, sized):
    ast = in_context(image(sized=sized), context)
    selected = schema(sized=sized)
    source = tm.from_dict(ast, schema=selected, strict=level)
    written = source.to_markdown()
    parsed = tm.from_markdown(written, schema=selected, html=html)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown() == written
    if context == "doc":
        assert written == ('<img src="/logo.png" alt="Logo" title="A logo" width="320" height="200"/>'
                           if sized else MARKDOWN_IMAGE)
    elif context == "table":
        assert written.startswith("| ")
        assert "\n| --- |" in written


@pytest.mark.parametrize("level", LEVELS)
def test_a_block_image_uses_paragraph_separation_between_other_blocks(level):
    ast = doc(p(text("Before")), image(), p(text("After")))
    selected = schema()
    source = tm.from_dict(ast, schema=selected, strict=level)
    written = source.to_markdown()
    assert written == f"Before\n\n{MARKDOWN_IMAGE}\n\nAfter"
    assert tm.from_markdown(written, schema=selected).to_dict() == source.to_dict()


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("parent", ("paragraph", "heading"))
def test_strict_uses_the_image_shape_for_inline_parent_content_checks(level, parent):
    attrs = {"level": 2} if parent == "heading" else None
    ast = doc(node(parent, image(), attrs=attrs))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema(), strict=level)
    assert_error(excinfo, "invalid_content", "content", "content[0].content[0]")


@pytest.mark.parametrize("parent", ("paragraph", "heading"))
def test_strict_off_keeps_the_existing_permissive_dict_content_boundary(parent):
    attrs = {"level": 2} if parent == "heading" else None
    ast = doc(node(parent, image(), attrs=attrs))
    assert tm.from_dict(ast, schema=schema(), strict="off").to_dict() == ast


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("marks", ([], [{"type": "bold"}]))
def test_strict_refuses_a_marks_field_on_a_block_image(level, marks):
    child = {**image(), "marks": marks}
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(child), schema=schema(), strict=level)
    assert_error(excinfo, "unknown_field", "marks", "content[0]")


@pytest.mark.parametrize("level", ("content", "exact"))
def test_a_markdown_table_cell_cannot_mix_a_block_image_with_another_block(level):
    ast = doc(node("table", node("tableRow", node("tableHeader", image(), p(text("After")))),
                   attrs={"colCount": 1}))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema(), strict=level)
    assert_error(excinfo, "unrepresentable", "content", "content[0].content[0].content[0].content[0]")


def test_content_expressions_resolve_image_as_a_block_type():
    selected = tm.Schema(block_image=True, nodes=[tm.NodeSpec("gallery", "block", content="image+")])
    ast = doc(node("gallery", image()))
    source = tm.from_dict(ast, schema=selected, strict="exact")
    assert tm.from_markdown(source.to_markdown(), schema=selected).to_dict() == source.to_dict()
    with pytest.raises(ValueError):
        tm.Schema(block_image=True, nodes=[tm.NodeSpec("caption", "inline", content="image*")])


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("carrier", (MARKDOWN_IMAGE, TAG_IMAGE))
@pytest.mark.parametrize("before, after", [("", ""), ("Before ", ""), ("", " After"),
                                         ("Before ", " After")])
def test_paragraphs_are_split_at_images_and_empty_fragments_are_omitted(html, carrier, before, after):
    selected = schema(sized=carrier == TAG_IMAGE)
    expected = []
    if before:
        expected.append(p(text(before.strip())))
    expected.append(image())
    if after:
        expected.append(p(text(after.strip())))
    parsed = tm.from_markdown(before + carrier + after, schema=selected, html=html)
    assert parsed.to_dict() == doc(*expected)
    assert tm.from_markdown(parsed.to_markdown(), schema=selected, html=html).to_dict() == parsed.to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("break_, space", [("\n", " "), ("  \n", "")])
def test_whitespace_and_breaks_touching_a_split_image_are_trimmed(html, break_, space):
    selected = schema()
    markdown = f"Before{space}{break_}{MARKDOWN_IMAGE}{break_}{space}After"
    parsed = tm.from_markdown(markdown, schema=selected, html=html)
    assert parsed.to_dict() == doc(p(text("Before")), image(), p(text("After")))
    assert tm.from_markdown(parsed.to_markdown(), schema=selected, html=html).to_dict() == parsed.to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markdown, path", [
    (f"**{MARKDOWN_IMAGE}**", "content[0]"),
    (f"[{MARKDOWN_IMAGE}](https://example.com)", "content[0]"),
    (f"**{TAG_IMAGE}**", ""),
])
def test_marked_markdown_images_are_errors_instead_of_losing_their_marks(html, markdown, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=schema(sized=TAG_IMAGE in markdown), html=html)
    assert_error(excinfo, "invalid_mark_set", "marks", path)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("table_tags", (False, True))
@pytest.mark.parametrize("markdown, path", [
    (f"# {MARKDOWN_IMAGE}", "content[0].content[0]"),
    (f"# {MARKDOWN_IMAGE} Title", "content[0].content[0]"),
    (f"| {MARKDOWN_IMAGE} Name |\n| --- |", "content[0].content[0].content[0].content[0].content[0]"),
    (f"| Heading |\n| --- |\n| {MARKDOWN_IMAGE} Name |", "content[0].content[1].content[0].content[0].content[0]"),
    (f"| Name {TAG_IMAGE} |\n| --- |", "content[0].content[0].content[0].content[0].content[1]"),
])
def test_images_in_headings_or_beside_other_cell_content_are_invalid(html, table_tags, markdown, path):
    selected = schema(sized=TAG_IMAGE in markdown)
    if table_tags:
        selected = selected.extend(core_attrs=tm.TABLE_SPANS)
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=selected, html=html)
    assert_error(excinfo, "invalid_content", "content", path)


@pytest.mark.parametrize("html", HTML)
def test_block_image_does_not_activate_img_without_an_image_overlay(html):
    baseline = tm.from_markdown(TAG_IMAGE, html=html)
    parsed = tm.from_markdown(TAG_IMAGE, schema=schema(), html=html)
    assert parsed.to_dict() == baseline.to_dict()
    assert parsed.to_dict()["content"][0]["type"] == ("htmlBlock" if html else "paragraph")


@pytest.mark.parametrize("html", HTML)
def test_an_image_overlay_activates_img_with_the_selected_block_shape(html):
    selected = schema(sized=True)
    parsed = tm.from_markdown(TAG_IMAGE, schema=selected, html=html)
    assert parsed.to_dict() == doc(image())
    assert parsed.to_markdown() == MARKDOWN_IMAGE


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("images", [MARKDOWN_IMAGE, "![A](a) ![B](b)"])
def test_images_without_surviving_text_cannot_discard_their_paragraphs_overlay(html, images):
    selected = tm.Schema(block_image=True, core_attrs=tm.TEXT_ALIGN)
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f'<p textAlign="center">{images}</p>', schema=selected, html=html)
    assert_error(excinfo, "invalid_content", "content", "content[0].content[0]")


@pytest.mark.parametrize("html", HTML)
def test_a_lone_block_image_cell_keeps_its_pipe_table_with_the_table_family_active(html):
    selected = tm.Schema(block_image=True, core_attrs=tm.TABLE_SPANS)
    source = tm.from_dict(in_context(image(), "table"), schema=selected, strict="exact")
    written = source.to_markdown()
    assert written == f"| {MARKDOWN_IMAGE} |\n| --- |"
    assert tm.from_markdown(written, schema=selected, html=html).to_dict() == source.to_dict()


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("cell", ("th", "td"))
def test_text_beside_an_image_is_refused_in_tag_table_cells(html, cell):
    selected = tm.Schema(block_image=True, core_attrs=tm.TABLE_SPANS)
    markdown = f"<table>\n\n<tr>\n\n<{cell}>\n\n{MARKDOWN_IMAGE} Name\n\n</{cell}>\n\n</tr>\n\n</table>"
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, schema=selected, html=html)
    assert_error(excinfo, "invalid_content", "content")


@pytest.mark.parametrize("entry", ("dict", "markdown"))
def test_uri_policy_still_applies_to_block_images(entry):
    selected = schema()
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if entry == "dict":
            tm.from_dict(doc(node("image", attrs={"src": "http://example.com/logo.png", "alt": ""})),
                         schema=selected, strict="exact", image_schemes=("https",))
        else:
            tm.from_markdown("![](http://example.com/logo.png)", schema=selected, image_schemes=("https",))
    assert_error(excinfo, "disallowed_scheme", "src", "content[0]")


@pytest.mark.parametrize("entry", ("dict", "markdown"))
def test_node_type_policy_still_applies_to_block_images(entry):
    selected = schema()
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        if entry == "dict":
            tm.from_dict(doc(image()), schema=selected, strict="exact", reject_node_types=("image",))
        else:
            tm.from_markdown(MARKDOWN_IMAGE, schema=selected, reject_node_types=("image",))
    assert_error(excinfo, "disallowed_node_type", "type", "content[0]")


@pytest.mark.parametrize("sized", (False, True))
def test_turning_the_option_off_keeps_the_inline_image_behavior(sized):
    selected = tm.Schema(block_image=False, core_attrs=tm.IMAGE_SIZE if sized else None)
    default = tm.Schema(core_attrs=tm.IMAGE_SIZE if sized else None)
    ast = doc(p(image(sized=sized)))
    source = tm.from_dict(ast, schema=selected, strict="exact")
    baseline = tm.from_dict(ast, schema=default, strict="exact")
    assert source.to_dict() == baseline.to_dict()
    assert source.to_markdown() == baseline.to_markdown()
    assert tm.from_markdown(source.to_markdown(), schema=selected).to_dict() == baseline.to_dict()
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(image()), schema=selected, strict="exact")
    assert_error(excinfo, "invalid_content", "content", "content[0]")
