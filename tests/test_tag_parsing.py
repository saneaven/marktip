"""Declared tags stay inside ordinary Markdown blocks."""

import pytest

import marktip as tm


BODIES = {
    "multiline": "<{tag}>\nfoo **bar**</{tag}>",
    "one_line": "<{tag}>x</{tag}>",
    "one_line_bold": "<{tag}>foo **bar**</{tag}>",
    "closing_line": "<{tag}>foo **bar**\n</{tag}>",
}
CONTEXTS = ("root", "tight", "loose", "quote", "after_paragraph")


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def paragraph(children):
    return {"type": "paragraph", "content": children}


def source(body, context):
    if context in ("tight", "loose"):
        value = "- " + body.replace("\n", "\n  ")
        return value + ("\n\n- next" if context == "loose" else "")
    if context == "quote":
        return "> " + body.replace("\n", "\n> ")
    if context == "after_paragraph":
        return "before\n" + body
    return body


def document(blocks, context):
    if context in ("tight", "loose"):
        items = [{"type": "listItem", "content": blocks}]
        if context == "loose":
            items.append({"type": "listItem", "content": [paragraph([text("next")])]})
        blocks = [{"type": "bulletList", "attrs": {"tight": context == "tight"}, "content": items}]
    elif context == "quote":
        blocks = [{"type": "blockquote", "content": blocks}]
    return {"type": "doc", "content": blocks}


def raw_children(tag, body, context, html):
    opening = {"type": "htmlInline", "attrs": {"html": f"<{tag}>"}}
    closing = {"type": "htmlInline", "attrs": {"html": f"</{tag}>"}}
    if body == "one_line":
        children = [opening, text("x"), closing]
    else:
        children = [opening, text("\nfoo " if body == "multiline" else "foo "), text("bar", "bold")]
        if body == "closing_line":
            children.append(text("\n"))
        children.append(closing)
    if context == "after_paragraph":
        children.insert(0, text("before\n"))
    if html:
        return children
    converted = []
    for child in children:
        if child["type"] == "htmlInline":
            child = text(child["attrs"]["html"])
        if converted and converted[-1].get("marks") == child.get("marks"):
            converted[-1]["text"] += child["text"]
        else:
            converted.append(child)
    return converted


def lifted_children(body, context):
    if body == "one_line":
        children = [text("x", "underline")]
    else:
        children = [text("\nfoo " if body == "multiline" else "foo ", "underline"),
                    text("bar", "bold", "underline")]
        if body == "closing_line":
            children.append(text("\n", "underline"))
    if context == "after_paragraph":
        children.insert(0, text("before\n"))
    return children


@pytest.mark.parametrize("tag", ("u", "summary"))
@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("body", BODIES)
def test_declared_tag_does_not_start_an_html_block(tag, html, context, body):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=tag)])
    markdown = source(BODIES[body].format(tag=tag), context)
    expected = document([paragraph(lifted_children(body, context))], context)
    assert tm.from_markdown(markdown, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("tag", ("u", "summary"))
@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("body", BODIES)
def test_undeclared_tags_keep_the_existing_block_structure(tag, html, context, body):
    value = BODIES[body].format(tag=tag)
    if html and (tag == "summary" or (body == "multiline" and context != "after_paragraph")):
        blocks = [{"type": "htmlBlock", "attrs": {"html": value + "\n"}}]
        if context == "after_paragraph":
            blocks.insert(0, paragraph([text("before")]))
    else:
        blocks = [paragraph(raw_children(tag, body, context, html))]
    expected = document(blocks, context)
    if context == "loose" and blocks[0]["type"] == "htmlBlock":
        expected["content"][0]["attrs"]["tight"] = True
    markdown = source(value, context)
    assert tm.from_markdown(markdown, html=html).to_dict() == expected
    other = tm.Schema(marks=[tm.MarkSpec("other")])
    assert tm.from_markdown(markdown, schema=other, html=html).to_dict() == expected


@pytest.mark.parametrize("tag", ("u", "summary"))
@pytest.mark.parametrize("html", (True, False))
def test_a_declared_closing_tag_at_line_start_reaches_the_inline_parent(tag, html):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=tag)])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(f"</{tag}>\nfoo **bar**", schema=schema, html=html)
    assert excinfo.value.code == "invalid_tag"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == "content[0]"


@pytest.mark.parametrize("declared, tag", [("u", "ul"), ("u", "u-other"), ("u", "U"), ("u-other", "u")])
@pytest.mark.parametrize("html", (True, False))
def test_line_start_tag_names_match_the_whole_declared_name_and_case(declared, tag, html):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=declared)])
    markdown = f"<{tag}>\nfoo **bar**</{tag}>"
    if html:
        blocks = [{"type": "htmlBlock", "attrs": {"html": markdown + "\n"}}]
    else:
        blocks = [paragraph(raw_children(tag, "multiline", "root", html))]
    assert tm.from_markdown(markdown, schema=schema, html=html).to_dict() == document(blocks, "root")


def test_declared_tag_line_inside_an_existing_html_block_stays_raw():
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag="u")])
    markdown = "<div>\n<u>foo **bar**</u>\n</div>"
    expected = document([{"type": "htmlBlock", "attrs": {"html": markdown + "\n"}}], "root")
    assert tm.from_markdown(markdown, schema=schema).to_dict() == expected


@pytest.mark.parametrize("tag", ("u", "summary"))
@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("context, prefix", [("quote", "> "), ("tight", "- ")])
def test_declared_tag_line_is_a_lazy_quote_or_list_continuation(tag, html, context, prefix):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=tag)])
    markdown = f"{prefix}before\n<{tag}>foo **bar**</{tag}>"
    children = [text("before\n"), text("foo ", "underline"), text("bar", "bold", "underline")]
    assert tm.from_markdown(markdown, schema=schema, html=html).to_dict() == document([paragraph(children)], context)


@pytest.mark.parametrize("tag", ("u", "summary"))
@pytest.mark.parametrize("html", (True, False))
def test_four_space_indented_declared_tags_stay_code(tag, html):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=tag)])
    body = f"<{tag}>foo **bar**</{tag}>"
    expected = document([{"type": "codeBlock", "content": [text(body + "\n")]}], "root")
    assert tm.from_markdown("    " + body, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("indent", ("", " ", "   "))
def test_strict_html_block_rejects_a_declared_tag_after_up_to_three_spaces(level, indent):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag="u")])
    ast = document([{"type": "htmlBlock", "attrs": {"html": indent + "<u>x</u>"}}], "root")
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert excinfo.value.code == "unrepresentable"
    assert excinfo.value.field == "html"
    assert excinfo.value.path == "content[0]"


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("declared, payload", [
    ("u", "    <u>x</u>"),
    ("u", "\t<u>x</u>"),
    ("u", "<ul>x</ul>"),
    ("u", "<u-other>x</u-other>"),
    ("u", "<U>x</U>"),
    ("u", "<u_foo>x</u_foo>"),
    ("u-other", "<u>x</u>"),
])
def test_strict_html_block_keeps_indented_or_different_tag_starts(level, declared, payload):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=declared)])
    ast = document([{"type": "htmlBlock", "attrs": {"html": payload}}], "root")
    assert tm.from_dict(ast, schema=schema, strict=level).to_dict() == ast


@pytest.mark.parametrize("tag", ("u", "summary"))
@pytest.mark.parametrize("html", (True, False))
@pytest.mark.parametrize("opening, tone", [
    ('<{tag}\ntone="red"\ncount=\n7\nflag>', "red"),
    ('<{tag} tone="red\nblue" count=7 flag>', "red\nblue"),
])
def test_declared_tags_accept_multiline_attrs(tag, html, opening, tone):
    schema = tm.Schema(marks=[tm.MarkSpec("underline", tag=tag,
                                        attrs={"tone": tm.Attr(str), "count": tm.Attr(int), "flag": tm.Attr(bool)})])
    markdown = opening.format(tag=tag) + f"foo **bar**</{tag}>"
    mark = {"type": "underline", "attrs": {"tone": tone, "count": 7, "flag": True}}
    children = [{"type": "text", "text": "foo ", "marks": [mark]},
                {"type": "text", "text": "bar", "marks": [{"type": "bold"}, mark]}]
    assert tm.from_markdown(markdown, schema=schema, html=html).to_dict() == document([paragraph(children)], "root")
