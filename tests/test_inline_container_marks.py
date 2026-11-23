"""Inline containers carry outer marks and start a fresh mark scope inside."""

import json

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
HTML = (True, False)


def doc(*children):
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(children)}]}


def text(value, *marks):
    result = {"type": "text", "text": value}
    if marks:
        result["marks"] = list(marks)
    return result


def container(*children, marks=()):
    result = {"type": "c"}
    if children:
        result["content"] = list(children)
    if marks:
        result["marks"] = list(marks)
    return result


def style(**attrs):
    result = {"type": "textStyle"}
    if attrs:
        result["attrs"] = attrs
    return result


def schema(*, required_color=False):
    return tm.Schema(nodes=[tm.NodeSpec("c", "inline", content="inline*")], marks=[
        tm.MarkSpec("textStyle", tag="span", attrs={
            "color": tm.Attr(str, inherit=True, required=required_color),
            "size": tm.Attr(str, inherit=True),
        }),
        tm.MarkSpec("underline", tag="u"),
    ])


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup, expected", (
    ('<span size="large">a <c>x</c> b</span>',
     doc(text("a ", style(size="large")), container(text("x"), marks=[style(size="large")]),
         text(" b", style(size="large")))),
    ('a <c><span size="large">x</span></c> b',
     doc(text("a "), container(text("x", style(size="large"))), text(" b"))),
    ("**a <c>x</c> b**",
     doc(text("a ", {"type": "bold"}), container(text("x"), marks=[{"type": "bold"}]),
         text(" b", {"type": "bold"}))),
    ("<c>**x**</c>", doc(container(text("x", {"type": "bold"})))),
    ('<span color="red"><c><span size="large">y</span></c></span>',
     doc(container(text("y", style(size="large")), marks=[style(color="red")]))),
))
def test_reading_table_keeps_outer_marks_on_the_container(html, markup, expected):
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
def test_required_inherited_attr_is_not_satisfied_across_a_container(html):
    markup = '<span color="red"><c><span size="large">y</span></c></span>'
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema(required_color=True), html=html)
    assert (excinfo.value.code, excinfo.value.field) == ("missing_attr", "color")


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("partial", (False, True))
@pytest.mark.parametrize("markup", (
    "<span>a <c>x</span> y</c>",
    "<c>a <span>b</c> c</span>",
    "**a <c>x** y</c>",
    "<c>a **b</c> c**",
    "*a <c>x* y</c>",
    "<c>a *b</c> c*",
    "~~a <c>x~~ y</c>",
    "<c>a ~~b</c> c~~",
    "[a <c>x](https://example.com) y</c>",
    "<c>a [b</c> c](https://example.com)",
    "**<c>**<u></u>**</c>**",
    "**<c>**<u>**x**</u>**</c>**",
))
def test_marks_cannot_cross_the_container_boundary(html, partial, markup):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=schema(), html=html, partial=partial)
    assert (excinfo.value.code, excinfo.value.field) == ("invalid_tag", "content")


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("outer, inner, mark", (
    ("*", "*", {"type": "italic"}),
    ("~~", "~~", {"type": "strike"}),
    ("[", "](https://example.com)", {"type": "link", "attrs": {"href": "https://example.com"}}),
))
def test_other_delimiter_marks_belong_to_the_container(html, outer, inner, mark):
    markup = outer + "a <c>x</c> b" + inner
    expected = doc(text("a ", mark), container(text("x"), marks=[mark]), text(" b", mark))
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
def test_nested_same_delimiter_is_read_as_the_container_mark(html):
    parsed = tm.from_markdown("**<c>**x**</c>**", schema=schema(), html=html)
    assert parsed.to_dict() == doc(container(text("x"), marks=[{"type": "bold"}]))
    assert parsed.to_markdown(canonical=True) == "**<c>x</c>**"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("reverse", (False, True))
def test_container_core_and_declared_marks_use_the_atom_order(html, level, reverse):
    marks = [{"type": "bold"}, {"type": "underline"}]
    if reverse:
        marks.reverse()
    source = tm.from_dict(doc(container(text("x"), marks=marks)), schema=schema(), strict=level)
    markup = "<u>**<c>x</c>**</u>"
    assert source.to_markdown(canonical=True) == markup
    assert tm.from_markdown(markup, schema=schema(), html=html).to_dict() == source.to_dict()


@pytest.mark.parametrize("html", HTML)
def test_outer_core_and_declared_marks_are_removed_together_from_inner_content(html):
    markup = "<u>**a<c><span>x</span></c>b**</u>"
    marks = [{"type": "bold"}, {"type": "underline"}]
    expected = doc(text("a", *marks), container(text("x", style()), marks=marks), text("b", *marks))
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
def test_goal_example_keeps_node_attrs_separate_from_outer_styles(html):
    custom_schema = tm.Schema(nodes=[tm.NodeSpec("customSpan", "inline", tag="custom-span", content="inline*",
                                               attrs={"class": tm.Attr(str), "color": tm.Attr(str)})],
                              marks=[schema().marks[0]])
    markup = ('<span color="red">a <custom-span class="k" color="blue">'
              'x <span size="large">y</span></custom-span></span>')
    expected = doc(text("a ", style(color="red")), {
        "type": "customSpan", "attrs": {"class": "k", "color": "blue"},
        "marks": [style(color="red")], "content": [text("x "), text("y", style(size="large"))],
    })
    parsed = tm.from_markdown(markup, schema=custom_schema, html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("own, child, markup", (
    (True, False, "<span><c>x</c></span>"),
    (False, True, "<c><span>x</span></c>"),
    (True, True, "<span><c><span>x</span></c></span>"),
))
def test_dict_marks_on_container_and_child_are_independent(html, level, own, child, markup):
    ast = doc(container(text("x", *([style()] if child else [])), marks=[style()] if own else []))
    source = tm.from_dict(ast, schema=schema(), strict=level)
    assert source.to_dict() == ast
    assert source.to_markdown(canonical=True) == markup
    assert tm.from_markdown(markup, schema=schema(), html=html).to_dict() == ast


@pytest.mark.parametrize("html", HTML)
def test_nested_containers_start_a_fresh_mark_scope_at_every_level(html):
    markup = ('<span color="red"><c><span size="large"><c>'
              '<span color="blue">x</span></c></span></c></span>')
    expected = doc(container(container(text("x", style(color="blue")), marks=[style(size="large")]),
                             marks=[style(color="red")]))
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == expected
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
def test_crossing_declared_marks_within_one_scope_still_work(html):
    markup = '<c><u>a <span>b</u> c</span></c>'
    underline = {"type": "underline"}
    expected = doc(container(text("a ", underline), text("b", style(), underline), text(" c", style())))
    assert tm.from_markdown(markup, schema=schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("html", HTML)
def test_same_kind_replacement_and_inheritance_work_within_the_container(html):
    markup = ('<span color="red"><c><span color="blue">a '
              '<span size="large">b</span> c</span></c></span>')
    expected = doc(container(text("a ", style(color="blue")), text("b", style(color="blue", size="large")),
                             text(" c", style(color="blue")), marks=[style(color="red")]))
    assert tm.from_markdown(markup, schema=schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("level", ("content", "exact"))
def test_code_mark_on_container_is_an_invalid_mark_set(level):
    ast = doc(container(text("x"), marks=[{"type": "code"}]))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema(), strict=level)
    assert (excinfo.value.code, excinfo.value.field, excinfo.value.path) == (
        "invalid_mark_set", "marks", "content[0].content[0]",
    )


@pytest.mark.parametrize("html", HTML)
def test_off_writes_container_outside_code_spans_and_drops_only_its_code_mark(html):
    code = {"type": "code"}
    ast = doc(text("a", code), container(text("x", code), marks=[code, style()]), text("b", code))
    source = tm.from_dict(ast, schema=schema(), strict="off")
    assert source.to_dict() == ast
    markup = "`a`<span><c>`x`</c></span>`b`"
    assert source.to_markdown(canonical=True) == markup
    expected = doc(text("a", code), container(text("x", code), marks=[style()]), text("b", code))
    assert tm.from_markdown(markup, schema=schema(), html=html).to_dict() == expected


@pytest.mark.parametrize("level", ("content", "exact"))
def test_container_marks_use_the_existing_mark_set_validation(level):
    ast = doc(container(text("x"), marks=[style(color="red"), style(size="large")]))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema(), strict=level)
    assert (excinfo.value.code, excinfo.value.path) == (
        "invalid_mark_set", "content[0].content[0].marks[1]",
    )


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("opening, closed", (
    ('<span color="red"><c>x', '<span color="red"><c>x</c></span>'),
    ('<c><span size="large">x', '<c><span size="large">x</span></c>'),
    ('<span color="red"><c><span size="large">x',
     '<span color="red"><c><span size="large">x</span></c></span>'),
    ('<span color="red"><c>x</c>', '<span color="red"><c>x</c></span>'),
))
def test_partial_closes_open_container_and_marks_in_their_own_scopes(html, opening, closed):
    actual = tm.from_markdown(opening, schema=schema(), html=html, partial=True)
    expected = tm.from_markdown(closed, schema=schema(), html=html)
    assert actual.to_dict() == expected.to_dict()
    assert actual.to_markdown(canonical=True) == closed


@pytest.mark.parametrize("html", HTML)
def test_container_marks_survive_storage_and_base_inheritance(html):
    current_schema = schema()
    markup = "<span color='red'><c><span size='large'>x</span></c></span>"
    original = tm.from_markdown(markup, schema=current_schema, html=html)
    stored = json.loads(json.dumps(original.dump()))
    loaded = tm.load(stored, schema=current_schema)
    assert loaded.to_dict() == original.to_dict()
    assert loaded.to_markdown() == markup
    assert loaded.dump() == stored
    inherited = tm.from_dict(loaded.to_dict(), schema=current_schema, base=loaded, strict="exact")
    assert inherited.to_dict() == original.to_dict()
    assert inherited.to_markdown() == markup
    assert inherited.to_markdown(canonical=True) == (
        '<span color="red"><c><span size="large">x</span></c></span>'
    )


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("mark, opening, closing", (
    ({"type": "bold"}, "**", "**"),
    ({"type": "italic"}, "*", "*"),
    ({"type": "strike"}, "~~", "~~"),
    ({"type": "link", "attrs": {"href": "https://example.com"}}, "[", "](https://example.com)"),
))
@pytest.mark.parametrize("shape", ("punctuation", "mixed", "atom", "marked-container", "unmarked-container"))
def test_writer_omits_equal_delimiter_marks_inside_marked_containers(html, level, mark, opening, closing, shape):
    current_schema = schema().extend(nodes=[
        tm.NodeSpec("d", "inline", content="inline*"), tm.NodeSpec("m", "inline"),
    ])
    if shape == "punctuation":
        children = [text("(x)", mark)]
        expected = [text("(x)")]
        body = r"\(x\)"
    elif shape == "mixed":
        children = [text("a"), text("b", mark)]
        expected = [text("ab")]
        body = "ab"
    elif shape == "atom":
        children = [{"type": "m", "marks": [mark]}]
        expected = [{"type": "m"}]
        body = "<m/>"
    elif shape == "marked-container":
        children = [{"type": "d", "marks": [mark], "content": [text("x")]}]
        expected = [{"type": "d", "content": [text("x")]}]
        body = "<d>x</d>"
    else:
        children = [{"type": "d", "content": [text("x", mark)]}]
        expected = [{"type": "d", "content": [text("x")]}]
        body = "<d>x</d>"
    ast = doc(container(*children, marks=[mark]))
    source = tm.from_dict(ast, schema=current_schema, strict=level)
    assert source.to_dict() == doc(container(*expected, marks=[mark]))
    markup = opening + "<c>" + body + "</c>" + closing
    assert source.to_markdown(canonical=True) == markup
    parsed = tm.from_markdown(markup, schema=current_schema, html=html)
    assert parsed.to_dict() == doc(container(*expected, marks=[mark]))
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("mark, opening, closing", (
    ({"type": "bold"}, "**", "**"),
    ({"type": "link", "attrs": {"href": "https://example.com"}}, "[", "](https://example.com)"),
))
def test_writer_groups_code_text_after_omitting_enclosing_container_marks(html, mark, opening, closing):
    code = {"type": "code"}
    ast = doc(container(text("a", code), text("b", code, mark), marks=[mark]))
    source = tm.from_dict(ast, schema=schema(), strict="exact")
    assert source.to_dict() == doc(container(text("ab", code), marks=[mark]))
    markup = opening + "<c>`ab`</c>" + closing
    assert source.to_markdown(canonical=True) == markup
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == doc(container(text("ab", code), marks=[mark]))
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("declared, opening, closing", (
    (style(color="red"), '<span color="red">', "</span>"),
    ({"type": "underline"}, "<u>", "</u>"),
))
def test_writer_preserves_declared_marks_when_omitting_equal_delimiter_marks(html, declared, opening, closing):
    bold = {"type": "bold"}
    ast = doc(container(text("x", bold, declared), marks=[bold, declared]))
    source = tm.from_dict(ast, schema=schema(), strict="exact")
    markup = opening + "**<c>" + opening + "x" + closing + "</c>**" + closing
    assert source.to_markdown(canonical=True) == markup
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == doc(container(text("x", declared), marks=[bold, declared]))
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
def test_writer_passes_delimiter_marks_from_each_enclosing_container(html):
    bold = {"type": "bold"}
    italic = {"type": "italic"}
    ast = doc(container(container(text("x", bold, italic), marks=[italic]), marks=[bold]))
    source = tm.from_dict(ast, schema=schema(), strict="exact")
    markup = "**<c>*<c>x</c>*</c>**"
    assert source.to_markdown(canonical=True) == markup
    parsed = tm.from_markdown(markup, schema=schema(), html=html)
    assert parsed.to_dict() == doc(container(container(text("x"), marks=[italic]), marks=[bold]))
    assert parsed.to_markdown(canonical=True) == markup


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("nested", (False, True))
@pytest.mark.parametrize("body", ("**", "x^*", "x~~y", "[0,1)", "x]y"))
@pytest.mark.parametrize("mark, opening, closing", (
    ({"type": "bold"}, "**", "**"),
    ({"type": "italic"}, "*", "*"),
    ({"type": "strike"}, "~~", "~~"),
    ({"type": "link", "attrs": {"href": "https://example.com"}}, "[", "](https://example.com)"),
))
def test_math_with_mark_syntax_uses_its_tag_inside_container_delimiters(html, nested, body, mark, opening, closing):
    current_schema = schema().extend(nodes=[tm.INLINE_MATH])
    math = {"type": "inlineMath", "attrs": {"latex": body}}
    child = container(math) if nested else math
    ast = doc(container(child, marks=[mark]))
    source = tm.from_dict(ast, schema=current_schema, strict="exact")
    math_tag = '<inlineMath latex="' + body + '"/>'
    inside = "<c>" + math_tag + "</c>" if nested else math_tag
    markup = opening + "<c>" + inside + "</c>" + closing
    assert source.to_markdown(canonical=True) == markup
    parsed = tm.from_markdown(markup, schema=current_schema, html=html)
    assert parsed.to_dict() == ast
    assert parsed.to_markdown(canonical=True) == markup
