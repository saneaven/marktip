"""Tag text uses the same node rules as dict input."""

import pytest

import marktip as tm


HTML = (True, False)
PARENT_PATH = "content[0]"


def doc(*children):
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(children)}]}


def text(value, marks=()):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def note_schema(container=False, **attrs):
    return tm.Schema(nodes=[tm.NodeSpec("note", kind="inline", content="inline*" if container else None,
                                       attrs=attrs)])


def carrier(attrs, container):
    return f"<note {attrs}>x</note>" if container else f"<note {attrs} />"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup", ("<note>", "<note/>", "<note />"))
def test_inline_atoms_accept_bare_and_self_closing_open_tags(html, markup):
    parsed = tm.from_markdown(markup, schema=note_schema(), html=html)
    assert parsed.to_dict() == doc({"type": "note"})
    assert parsed.to_markdown(canonical=True) == "<note/>"


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("markup", ("</note>", "</note/>", "<note></note>"))
def test_inline_atoms_refuse_closing_tags(html, markup):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markup, schema=note_schema(), html=html)
    assert excinfo.value.code == "invalid_tag"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("container", (False, True))
@pytest.mark.parametrize("attrs, values", (
    ("name='a&amp;b' number=+7 enabled", {"name": "a&b", "number": 7, "enabled": True}),
    ('name="c&lt;d" number="-9" enabled=false', {"name": "c<d", "number": -9, "enabled": False}),
    ("name=plain number=0 enabled=true", {"name": "plain", "number": 0, "enabled": True}),
    ("name='' number='-0' enabled='false'", {"name": "", "number": 0, "enabled": False}),
))
def test_inline_node_attrs_decode_all_html_value_forms(html, container, attrs, values):
    schema = note_schema(container, name=tm.Attr(str), number=tm.Attr(int), enabled=tm.Attr(bool))
    node = {"type": "note", "attrs": values}
    if container:
        node["content"] = [text("x")]
    assert tm.from_markdown(carrier(attrs, container), schema=schema, html=html).to_dict() == doc(node)


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("container", (False, True))
def test_inline_node_attrs_elide_explicit_defaults_when_read(html, container):
    schema = note_schema(container, tone=tm.Attr(str, choices=("red", "blue"), default="red"),
                         number=tm.Attr(int, default=0), enabled=tm.Attr(bool, default=False))
    node = {"type": "note"}
    if container:
        node["content"] = [text("x")]
    parsed = tm.from_markdown(carrier('tone="red" number=0 enabled=false', container), schema=schema, html=html)
    assert parsed.to_dict() == doc(node)
    assert parsed.to_markdown(canonical=True) == ("<note>x</note>" if container else "<note/>")


@pytest.mark.parametrize("html", HTML)
@pytest.mark.parametrize("container", (False, True))
@pytest.mark.parametrize("attrs, code, field", (
    ("", "missing_attr", "id"),
    ("id", "invalid_attr_value", "id"),
    ("id='u1' unknown='x'", "unknown_attr", "unknown"),
    ("id='u1' id='u2'", "invalid_attr_value", "id"),
    ("id='u1' tone='green'", "invalid_attr_value", "tone"),
    ("id='u1' number='7x'", "invalid_attr_value", "number"),
    ("id='u1' number='9223372036854775808'", "invalid_attr_value", "number"),
    ("id='u1' enabled='yes'", "invalid_attr_value", "enabled"),
))
def test_inline_node_tag_attrs_keep_located_validation_errors(html, container, attrs, code, field):
    schema = note_schema(container, id=tm.Attr(str, required=True),
                         tone=tm.Attr(str, choices=("red", "blue")), number=tm.Attr(int), enabled=tm.Attr(bool))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(carrier(attrs, container), schema=schema, html=html)
    assert excinfo.value.code == code
    assert excinfo.value.field == field
    assert excinfo.value.path == PARENT_PATH


@pytest.mark.parametrize("html", HTML)
def test_unknown_html_inside_a_container_keeps_marks_and_merges_as_literal_text_when_disabled(html):
    schema = tm.Schema(nodes=[tm.NodeSpec("wrap", kind="inline", content="inline*")],
                       marks=[tm.MarkSpec("zeta"), tm.MarkSpec("alpha")])
    markup = "<wrap><alpha><zeta>**a<span>b</span>c**</zeta></alpha></wrap>"
    marks = [{"type": "bold"}, {"type": "zeta"}, {"type": "alpha"}]
    if html:
        children = [text("a", marks), {"type": "htmlInline", "attrs": {"html": "<span>"}, "marks": marks},
                    text("b", marks), {"type": "htmlInline", "attrs": {"html": "</span>"}, "marks": marks},
                    text("c", marks)]
    else:
        children = [text("a<span>b</span>c", marks)]
    assert tm.from_markdown(markup, schema=schema, html=html).to_dict() == doc({"type": "wrap", "content": children})


@pytest.mark.parametrize("html", HTML)
def test_adjacent_text_merges_inside_containers_after_empty_mark_pairs(html):
    schema = tm.Schema(nodes=[tm.NodeSpec("wrap", kind="inline", content="inline*"),
                              tm.NodeSpec("inner", kind="inline", content="inline*")],
                       marks=[tm.MarkSpec("underline", tag="u")])
    markup = "<wrap>a<u></u>b<inner></inner>c<u></u>d</wrap>"
    expected = doc({"type": "wrap", "content": [text("ab"), {"type": "inner"}, text("cd")]})
    assert tm.from_markdown(markup, schema=schema, html=html).to_dict() == expected
