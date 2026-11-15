"""Preset declarations accept the JSON emitted by the corresponding Tiptap extensions."""

import json
from importlib.resources import files

import pytest

import marktip as tm


def doc(*children):
    return {"type": "doc", "content": list(children)}


def node(type_, *children, attrs=None):
    result = {"type": type_}
    if attrs is not None:
        result["attrs"] = attrs
    if children:
        result["content"] = list(children)
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


def preset_schema():
    return tm.Schema(
        marks=[tm.UNDERLINE, tm.HIGHLIGHT, tm.SUBSCRIPT, tm.SUPERSCRIPT, tm.TEXT_STYLE],
        nodes=[tm.MENTION, *tm.DETAILS, tm.INLINE_MATH, tm.BLOCK_MATH],
        core_attrs={**tm.TEXT_ALIGN, **tm.LINK_ATTRS, **tm.IMAGE_SIZE, **tm.TABLE_SPANS},
    )


@pytest.mark.parametrize("name", ("UNDERLINE", "HIGHLIGHT", "SUBSCRIPT", "SUPERSCRIPT", "TEXT_STYLE"))
def test_mark_presets_are_mark_declarations(name):
    preset = getattr(tm, name)
    assert isinstance(preset, tm.MarkSpec)
    assert tm.Schema(marks=[preset]).marks == (preset,)


@pytest.mark.parametrize("name", ("MENTION", "INLINE_MATH", "BLOCK_MATH"))
def test_node_presets_are_node_declarations(name):
    preset = getattr(tm, name)
    assert isinstance(preset, tm.NodeSpec)
    assert tm.Schema(nodes=[preset]).nodes == (preset,)


def test_details_is_a_tuple_of_three_node_declarations():
    assert isinstance(tm.DETAILS, tuple)
    assert [node.name for node in tm.DETAILS] == ["details", "detailsSummary", "detailsContent"]
    assert all(isinstance(node, tm.NodeSpec) for node in tm.DETAILS)
    assert tm.Schema(nodes=tm.DETAILS).nodes == tm.DETAILS


@pytest.mark.parametrize("name", ("TEXT_ALIGN", "LINK_ATTRS", "IMAGE_SIZE", "TABLE_SPANS"))
def test_core_attr_presets_are_plain_mappings(name):
    preset = getattr(tm, name)
    assert isinstance(preset, dict)
    assert all(isinstance(attrs, dict) for attrs in preset.values())
    assert all(isinstance(attr, tm.Attr) for attrs in preset.values() for attr in attrs.values())
    assert tm.Schema(core_attrs=preset).core_attrs == preset


@pytest.mark.parametrize("name", (
    "UNDERLINE", "HIGHLIGHT", "SUBSCRIPT", "SUPERSCRIPT", "TEXT_STYLE", "MENTION", "DETAILS",
    "INLINE_MATH", "BLOCK_MATH", "TEXT_ALIGN", "LINK_ATTRS", "IMAGE_SIZE", "TABLE_SPANS",
))
def test_every_preset_constant_equals_its_data_file_entry(name):
    entries = json.loads(files("marktip").joinpath("presets.json").read_text(encoding="utf-8"))
    preset = getattr(tm, name)
    if isinstance(preset, tm.MarkSpec):
        schema = tm.Schema(marks=[preset])
    elif isinstance(preset, tm.NodeSpec):
        schema = tm.Schema(nodes=[preset])
    elif isinstance(preset, tuple):
        schema = tm.Schema(nodes=preset)
    else:
        schema = tm.Schema(core_attrs=preset)
    assert tm.Schema.from_dict(entries[name]) == schema


def test_preset_mark_decoder_reads_json_exclusion_lists_like_schema_from_dict(monkeypatch):
    from marktip import presets

    entry = {"marks": [{"name": "note", "excludes": ["bold"],
                        "attrs": {"tone": {"type": "str", "choices": ["red", "blue"], "default": "red"}}}]}
    monkeypatch.setitem(presets._DATA, "NOTE", entry)
    preset = presets._mark("NOTE")
    assert preset.excludes == ("bold",)
    assert tm.Schema(marks=[preset]) == tm.Schema.from_dict(entry)


def test_preset_schema_declarations_survive_json_and_extend():
    schema = preset_schema()
    rebuilt = tm.Schema.from_dict(json.loads(json.dumps(schema.to_dict())))
    assert rebuilt == schema
    assert hash(rebuilt) == hash(schema)
    base = tm.Schema(marks=schema.marks, nodes=schema.nodes, core_attrs=tm.LINK_ATTRS)
    extended = base.extend(core_attrs=tm.IMAGE_SIZE).extend(core_attrs=tm.TABLE_SPANS)
    extended = extended.extend(core_attrs=tm.text_align(types=("paragraph", "heading")))
    assert extended.to_dict()["core_attrs"] == {
        **tm.Schema(core_attrs=tm.LINK_ATTRS).to_dict()["core_attrs"],
        **tm.Schema(core_attrs=tm.IMAGE_SIZE).to_dict()["core_attrs"],
        **tm.Schema(core_attrs=tm.TABLE_SPANS).to_dict()["core_attrs"],
        **tm.Schema(core_attrs=tm.text_align(types=("paragraph", "heading"))).to_dict()["core_attrs"],
    }


@pytest.mark.parametrize("html", (True, False))
def test_tiptap_json_with_inline_images_roundtrips_with_presets_under_exact(html):
    """The image uses Image.configure({inline: true})."""
    schema = preset_schema()
    paragraph = node(
        "paragraph",
        text("Underline", mark("underline")), text(" "),
        text("highlight", mark("highlight", color="#ffff00")), text(" "),
        text("subscript", mark("subscript")), text(" "),
        text("superscript", mark("superscript")), text(" "),
        text("styled", mark("textStyle", backgroundColor="#eeeeee", color="#123456",
                            fontFamily="Inter", fontSize="18px", lineHeight="1.5")),
        text(" "), node("mention", attrs={"id": "user-1", "label": "Ada", "mentionSuggestionChar": "@"}),
        text(" "), node("inlineMath", attrs={"latex": "x^2"}), text("."),
        attrs={"textAlign": "center"},
    )
    link = mark("link", href="https://example.com/docs", title=None, target="_self", rel="nofollow",
                **{"class": None})
    image = node("image", attrs={"src": "https://example.com/chart.png", "alt": "A chart", "title": None,
                                "width": 640, "height": 360})
    spans = {"colspan": 1, "rowspan": 1, "colwidth": None, "align": None}
    table = node(
        "table",
        node("tableRow", node("tableHeader", node("paragraph", text("Merged heading")),
                              attrs={"colspan": 2, "rowspan": 1, "colwidth": [120, 140], "align": None})),
        node("tableRow", node("tableCell", node("paragraph", text("Left")), attrs=spans),
                         node("tableCell", node("paragraph", text("Right")), attrs=spans)),
    )
    details = node("details", node("detailsSummary", text("More information")),
                   node("detailsContent", node("paragraph", text("The details body."))), attrs={"open": True})
    ast = doc(paragraph, node("heading", text("Aligned heading"), attrs={"level": 2, "textAlign": "right"}),
              node("paragraph", text("Documentation", link)), node("paragraph", image), table, details,
              node("blockMath", attrs={"latex": r"E = mc^2"}))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    written = source.to_markdown()
    parsed = tm.from_markdown(written, schema=schema, html=html)
    assert parsed.to_dict() == source.to_dict()
    assert parsed.to_markdown() == written


@pytest.mark.parametrize("html", (True, False))
def test_stock_defaults_are_unset_even_under_exact(html):
    schema = preset_schema()
    ast = doc(node("paragraph", text("Link", mark("link", href="https://example.com", target="_blank",
                                                  rel="noopener noreferrer nofollow", **{"class": None})),
                   text(" "), node("mention", attrs={"id": "user-1", "label": None, "mentionSuggestionChar": "@"}),
                   attrs={"textAlign": None}),
              node("blockMath", attrs={"latex": ""}))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    paragraph = source.to_dict()["content"][0]
    assert "attrs" not in paragraph
    assert paragraph["content"][0]["marks"] == [mark("link", href="https://example.com")]
    assert paragraph["content"][2]["attrs"] == {"id": "user-1"}
    assert source.to_dict()["content"][1] == {"type": "blockMath"}
    parsed = tm.from_markdown(source.to_markdown(), schema=schema, html=html)
    assert parsed.to_dict() == source.to_dict()


def test_text_align_uses_the_documented_paragraph_and_heading_targets():
    assert set(tm.TEXT_ALIGN) == {"paragraph", "heading"}
    assert tm.TEXT_ALIGN == tm.text_align()
    configured = tm.text_align(types=("paragraph", "heading"), default_alignment="left")
    schema = tm.Schema(core_attrs=configured)
    ast = doc(node("paragraph", text("x"), attrs={"textAlign": "left"}))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    assert source.to_dict() == doc(node("paragraph", text("x")))
    assert source.to_markdown() == "x"


def test_preset_constants_declare_the_optional_extension_attrs():
    assert tm.TEXT_STYLE == tm.text_style()
    assert tm.LINK_ATTRS == tm.link_attrs()
    assert tm.HIGHLIGHT.attrs == {"color": tm.Attr(str)}
    assert tm.DETAILS[0].attrs == {"open": tm.Attr(bool, default=False)}
    assert list(tm.TEXT_STYLE.attrs) == ["backgroundColor", "color", "fontFamily", "fontSize", "lineHeight"]


def test_configured_text_style_only_declares_the_enabled_extension_attrs():
    configured = tm.text_style(background_color=False, font_family=False, font_size=False, line_height=False)
    assert configured.attrs == {"color": tm.Attr(str)}
    schema = tm.Schema(marks=[configured])
    ast = doc(node("paragraph", text("x", mark("textStyle", color="red"))))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    assert tm.from_markdown(source.to_markdown(), schema=schema).to_dict() == source.to_dict()


def test_configured_text_align_checks_the_editors_alignment_options():
    schema = tm.Schema(core_attrs=tm.text_align(types=("paragraph",), alignments=("left", "right")))
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(node("paragraph", text("x"), attrs={"textAlign": "center"})),
                     schema=schema, strict="exact")
    assert (excinfo.value.code, excinfo.value.field, excinfo.value.path) == (
        "invalid_attr_value", "textAlign", "content[0]",
    )


def test_configured_link_defaults_follow_the_editor_html_attributes():
    schema = tm.Schema(core_attrs=tm.link_attrs(target="_self", rel="nofollow", class_="reference"))
    ast = doc(node("paragraph", text("Link", mark("link", href="https://example.com", target="_self",
                                                rel="nofollow", **{"class": "reference"}))))
    source = tm.from_dict(ast, schema=schema, strict="exact")
    assert source.to_dict() == doc(node("paragraph", text("Link", mark("link", href="https://example.com"))))
    assert source.to_markdown() == "[Link](https://example.com)"
