"""Fence and math carriers preserve their declared nodes and tag fallbacks."""

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value):
    return {"type": "text", "text": value}


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


def inline_schema(*, marks=()):
    return tm.Schema(marks=marks, nodes=[
        tm.NodeSpec("inlineMath", kind="inline", math="inline", body="latex",
                    attrs={"latex": tm.Attr(str), "label": tm.Attr(str)}),
    ])


def block_schema(*, display=False, fence=True):
    return tm.Schema(nodes=[
        tm.NodeSpec("blockMath", kind="block", fence="math" if fence else None,
                    math="display" if display else None, body="latex",
                    attrs={"latex": tm.Attr(str), "label": tm.Attr(str)}),
    ])


def roundtrip(ast, schema, markdown, html, level, **options):
    source = tm.from_dict(ast, schema=schema, strict=level, **options)
    written = source.to_markdown(canonical=True)
    if markdown is not None:
        assert written == markdown
    parsed = tm.from_markdown(written, schema=schema, html=html, **options)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown(canonical=True) == written
    return parsed


def inline_context(child, context, written):
    if context == "paragraph":
        return doc(p(child)), written
    if context == "heading":
        return doc(node("heading", child, attrs={"level": 2})), "## " + written
    if context == "quote":
        return doc(node("blockquote", p(child))), "> " + written
    if context == "bullet":
        ast = doc(node("bulletList", node("listItem", p(child)), attrs={"tight": True}))
        return ast, "- " + written
    if context == "ordered":
        ast = doc(node("orderedList", node("listItem", p(child)), attrs={"start": 3, "tight": True}))
        return ast, "3. " + written
    if context == "task":
        ast = doc(node("taskList", node("taskItem", p(child), attrs={"checked": True}),
                       attrs={"tight": True}))
        return ast, "- [x] " + written
    ast = doc(node("table", node("tableRow", node("tableHeader", p(child))), attrs={"colCount": 1}))
    return ast, f"| {written} |\n| --- |"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("body, markdown", [
    ("", "```math\n\n```"),
    ("x + y", "```math\nx + y\n```"),
    ("x\n", "```math\nx\n\n```"),
    ("x\n\n", "```math\nx\n\n\n```"),
    (r"\text{`code`}", "```math\n\\text{`code`}\n```"),
    ("~~~", "```math\n~~~\n```"),
])
def test_fence_body_keeps_empty_values_and_each_existing_final_newline(html, level, body, markdown):
    roundtrip(doc(node("blockMath", attrs={"latex": body})), block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_fence_delimiter_is_longer_than_a_backtick_run_in_the_body(html, level):
    body = "before\n```\nafter"
    markdown = "````math\nbefore\n```\nafter\n````"
    roundtrip(doc(node("blockMath", attrs={"latex": body})), block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("attrs, markdown", [
    ({}, "<blockMath/>"),
    ({"latex": None}, "<blockMath/>"),
    ({"latex": "x\ry"}, '<blockMath latex="x&#13;y"/>'),
    ({"latex": "x", "label": "named"}, '<blockMath latex="x" label="named"/>'),
])
def test_fence_falls_back_to_a_tag_when_the_body_form_cannot_carry_the_attrs(html, level, attrs, markdown):
    roundtrip(doc(node("blockMath", attrs=attrs)), block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_fence_defaults_are_elided_before_choosing_the_form(html, level):
    schema = tm.Schema(nodes=[tm.NodeSpec("blockMath", "block", fence="math", body="latex", attrs={
        "latex": tm.Attr(str, default="zero"), "label": tm.Attr(str, default="plain"),
    })])
    roundtrip(doc(node("blockMath", attrs={"latex": "zero"})), schema, "<blockMath/>", html, level)
    roundtrip(doc(node("blockMath", attrs={"latex": "x", "label": "plain"})),
              schema, "```math\nx\n```", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("context", ("root", "quote", "bullet", "ordered", "task"))
def test_fences_roundtrip_in_block_contexts(html, level, context):
    child = node("blockMath", attrs={"latex": "x + y"})
    if context == "root":
        ast, markdown = doc(child), "```math\nx + y\n```"
    elif context == "quote":
        ast, markdown = doc(node("blockquote", child)), "> ```math\n> x + y\n> ```"
    elif context == "bullet":
        ast = doc(node("bulletList", node("listItem", child), attrs={"tight": True}))
        markdown = "- ```math\n  x + y\n  ```"
    elif context == "ordered":
        ast = doc(node("orderedList", node("listItem", child), attrs={"start": 3, "tight": True}))
        markdown = "3. ```math\n   x + y\n   ```"
    else:
        ast = doc(node("taskList", node("taskItem", child, attrs={"checked": True}), attrs={"tight": True}))
        markdown = "- [x]\n  ```math\n  x + y\n  ```"
    roundtrip(ast, block_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_fences_use_the_single_line_tag_form_in_table_cells(html, level):
    child = node("blockMath", attrs={"latex": "x\ny"})
    ast = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
    roundtrip(ast, block_schema(), '| <blockMath latex="x&#10;y"/> |\n| --- |', html, level)


@pytest.mark.parametrize("html", HTML)
def test_readable_fence_separates_tables_in_a_list_item(html):
    table = node("table", node("tableRow", node("tableHeader", p(text("h")))),
                 node("tableRow", node("tableCell", p(text("v")))), attrs={"colCount": 1})
    ast = doc(node("bulletList",
                   node("listItem", table, node("blockMath", attrs={"latex": "x"}), table),
                   node("listItem", p(text("after"))), attrs={"tight": False}))
    markdown = ("- | h |\n  | --- |\n  | v |\n\n  ```math\n  x\n  ```\n"
                "  | h |\n  | --- |\n  | v |\n\n- after")
    roundtrip(ast, block_schema(), markdown, html, "exact")


@pytest.mark.parametrize("html", HTML)
def test_both_the_fence_and_tag_forms_read_as_the_same_declared_block(html):
    schema = block_schema()
    expected = doc(node("blockMath", attrs={"latex": "x + y"}))
    for markdown in ("```math\nx + y\n```", '<blockMath latex="x + y"/>'):
        parsed = tm.from_markdown(markdown, schema=schema, html=html)
        assert parsed.to_dict() == expected
        assert parsed.to_markdown(canonical=True) == "```math\nx + y\n```"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("context", ("paragraph", "heading", "quote", "bullet", "ordered", "task", "table"))
def test_inline_math_uses_dollars_in_inline_contexts(html, level, context):
    ast, markdown = inline_context(node("inlineMath", attrs={"latex": "x + y"}), context, "$x + y$")
    roundtrip(ast, inline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("body", (r"\alpha + \beta", "x &amp; y", " x + y ", "x\\\\"))
def test_inline_math_body_is_written_and_read_raw(html, level, body):
    roundtrip(doc(p(node("inlineMath", attrs={"latex": body}))), inline_schema(), f"${body}$", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("attrs, markdown", [
    ({}, "<inlineMath/>"),
    ({"latex": ""}, '<inlineMath latex=""/>'),
    ({"latex": "x\ny"}, '<inlineMath latex="x&#10;y"/>'),
    ({"latex": "x\ry"}, '<inlineMath latex="x&#13;y"/>'),
    ({"latex": "x$y"}, '<inlineMath latex="x$y"/>'),
    ({"latex": "`x`"}, '<inlineMath latex="&#96;x&#96;"/>'),
    ({"latex": "x\\"}, r'<inlineMath latex="x\"/>'),
    ({"latex": "x", "label": "named"}, '<inlineMath latex="x" label="named"/>'),
])
def test_inline_math_uses_its_tag_when_dollars_would_change_the_node(html, level, attrs, markdown):
    roundtrip(doc(p(node("inlineMath", attrs=attrs))), inline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("before, after, markdown", [
    ("a ", ", next", "a $x$, next"),
    ("한글 ", " 다음", "한글 $x$ 다음"),
    ("가", "나", '가<inlineMath latex="x"/>나'),
    ("a", "b", 'a<inlineMath latex="x"/>b'),
    ("$", "$", '\\$<inlineMath latex="x"/>\\$'),
])
def test_inline_math_form_depends_on_its_written_neighbours(html, level, before, after, markdown):
    ast = doc(p(text(before), node("inlineMath", attrs={"latex": "x"}), text(after)))
    roundtrip(ast, inline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_adjacent_inline_math_atoms_do_not_merge_into_one_span(html, level):
    ast = doc(p(node("inlineMath", attrs={"latex": "x"}), node("inlineMath", attrs={"latex": "y"})))
    roundtrip(ast, inline_schema(), None, html, level)


@pytest.mark.parametrize("html", HTML)
def test_inline_math_uses_container_tags_as_written_boundaries(html):
    schema = inline_schema().extend(nodes=[tm.NodeSpec("wrap", kind="inline", content="inline*")])
    ast = doc(p(text("a"), node("wrap", node("inlineMath", attrs={"latex": "x"})), text("b")))
    roundtrip(ast, schema, "a<wrap>$x$</wrap>b", html, "exact")


@pytest.mark.parametrize("html", HTML)
def test_inline_math_uses_textblock_tags_as_written_boundaries(html):
    schema = inline_schema().extend(nodes=[tm.NodeSpec("lead", kind="block", content="inline*")])
    ast = doc(node("lead", node("inlineMath", attrs={"latex": "x"})))
    roundtrip(ast, schema, "<lead>$x$</lead>", html, "exact")


@pytest.mark.parametrize("html", HTML)
def test_inline_math_between_hard_breaks_keeps_its_line_boundaries(html):
    ast = doc(p(text("before"), node("hardBreak"), node("inlineMath", attrs={"latex": "x"}),
                node("hardBreak"), text("after")))
    roundtrip(ast, inline_schema(), "before  \n$x$  \nafter", html, "exact")


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("core, markdown", [
    (mark("bold"), "**$x$**"),
    (mark("italic"), "*$x$*"),
    (mark("strike"), "~~$x$~~"),
    (mark("link", href="https://example.com"), "[$x$](https://example.com)"),
])
def test_inline_math_keeps_core_and_declared_marks(html, level, core, markdown):
    schema = inline_schema(marks=[tm.MarkSpec("underline", tag="u")])
    roundtrip(doc(p(node("inlineMath", attrs={"latex": "x"}, marks=[core]))),
              schema, markdown, html, level)
    roundtrip(doc(p(node("inlineMath", attrs={"latex": "x"}, marks=[mark("underline"), core]))),
              schema, f"<u>{markdown}</u>", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_pipe_in_inline_math_uses_a_tag_in_a_table_cell(html, level):
    child = node("inlineMath", attrs={"latex": "x|y"})
    ast, markdown = inline_context(child, "table", '<inlineMath latex="x&#124;y"/>')
    roundtrip(ast, inline_schema(), markdown, html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
def test_math_schema_escapes_literal_dollars_in_text_and_image_alt(html, level):
    schema = inline_schema()
    ast = doc(p(text("cost $5 and "), node("inlineMath", attrs={"latex": "x"}), text(" with tax $1")))
    roundtrip(ast, schema, r"cost \$5 and $x$ with tax \$1", html, level)
    image = node("image", attrs={"src": "image.png", "alt": "$x$"})
    roundtrip(doc(p(image)), schema, r"![\$x\$](image.png)", html, level)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("declared_mode, source, alt", [
    ("inline", "$x + y$", "x + y"),
    ("display", "$$x + y$$", "x + y"),
    ("inline", "$$**x**$$", "$$**x**$$"),
    ("display", "$**x**$", "$**x**$"),
])
def test_image_alt_flattens_declared_math_but_keeps_undeclared_mode_literal(html, declared_mode, source, alt):
    schema = inline_schema() if declared_mode == "inline" else block_schema(display=True, fence=False)
    parsed = tm.from_markdown(f"![value {source}](image.png)", schema=schema, html=html)
    expected = doc(p(node("image", attrs={"src": "image.png", "alt": "value " + alt})))
    assert parsed.to_dict() == expected
    written = parsed.to_markdown(canonical=True)
    reparsed = tm.from_markdown(written, schema=schema, html=html)
    assert reparsed.to_dict() == expected
    assert reparsed.to_markdown(canonical=True) == written


@pytest.mark.parametrize("html", HTML)
def test_fence_only_schema_does_not_turn_dollars_into_math(html):
    schema = block_schema()
    parsed = tm.from_markdown("$x$", schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text("$x$")))
    assert parsed.to_markdown(canonical=True) == "$x$"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("fence, markdown", [(False, '<blockMath latex="x + y"/>'),
                                            (True, "```math\nx + y\n```")])
def test_display_math_is_read_as_a_block_but_never_written_with_double_dollars(html, fence, markdown):
    schema = block_schema(display=True, fence=fence)
    parsed = tm.from_markdown("$$x + y$$", schema=schema, html=html)
    expected = doc(node("blockMath", attrs={"latex": "x + y"}))
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markdown
    assert tm.from_markdown(markdown, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
def test_a_whole_display_span_becomes_a_block_even_with_a_mark_on_the_span(html):
    schema = block_schema(display=True, fence=False)
    parsed = tm.from_markdown("**$$x$$**", schema=schema, html=html)
    assert parsed.to_dict() == doc(node("blockMath", attrs={"latex": "x"}))


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("context", ("quote", "bullet", "table"))
def test_display_math_reads_from_a_whole_paragraph_in_block_contexts(html, context):
    schema = block_schema(display=True, fence=False)
    child = node("blockMath", attrs={"latex": "x"})
    if context == "quote":
        source, expected, written = "> $$x$$", doc(node("blockquote", child)), '> <blockMath latex="x"/>'
    elif context == "bullet":
        source = "- $$x$$"
        expected = doc(node("bulletList", node("listItem", child), attrs={"tight": True}))
        written = '- <blockMath latex="x"/>'
    else:
        source = "| $$x$$ |\n| --- |"
        expected = doc(node("table", node("tableRow", node("tableHeader", child)), attrs={"colCount": 1}))
        written = '| <blockMath latex="x"/> |\n| --- |'
    parsed = tm.from_markdown(source, schema=schema, html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == written
    assert tm.from_markdown(written, schema=schema, html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("mode, source", [("inline", "$$**x**$$"), ("display", "$**x**$")])
def test_undeclared_math_mode_is_literal_including_its_unparsed_markdown(html, mode, source):
    schema = inline_schema() if mode == "inline" else block_schema(display=True, fence=False)
    parsed = tm.from_markdown(source, schema=schema, html=html)
    assert parsed.to_dict() == doc(p(text(source)))
    written = parsed.to_markdown(canonical=True)
    assert tm.from_markdown(written, schema=schema, html=html).to_dict() == parsed.to_dict()
    assert tm.from_markdown(written, schema=schema, html=html).to_markdown(canonical=True) == written
