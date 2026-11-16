import pytest

import marktip as tm


SCHEMA = tm.Schema(marks=[tm.TEXT_STYLE, tm.UNDERLINE])


def runs(markdown, schema=SCHEMA, **options):
    paragraph = tm.from_markdown(markdown, schema=schema, **options).to_dict()["content"][0]
    return [
        (node["text"], {mark["type"]: mark.get("attrs", {}) for mark in node.get("marks", [])})
        for node in paragraph["content"]
    ]


def test_a_nested_span_keeps_the_outer_styles_it_does_not_write():
    assert runs('<span color="red">a <span fontSize="12px">b</span> c</span>') == [
        ("a ", {"textStyle": {"color": "red"}}),
        ("b", {"textStyle": {"color": "red", "fontSize": "12px"}}),
        (" c", {"textStyle": {"color": "red"}}),
    ]


def test_a_nested_span_overrides_the_style_it_writes():
    assert runs('<span color="red" fontSize="12px">a <span color="blue">b</span></span>') == [
        ("a ", {"textStyle": {"color": "red", "fontSize": "12px"}}),
        ("b", {"textStyle": {"color": "blue", "fontSize": "12px"}}),
    ]


def test_styles_accumulate_through_every_level_and_unwind_in_order():
    markdown = '<span color="red">a <span fontSize="12px">b <span lineHeight="2">c</span> d</span> e</span>'

    assert [marks["textStyle"] for _, marks in runs(markdown)] == [
        {"color": "red"},
        {"color": "red", "fontSize": "12px"},
        {"color": "red", "fontSize": "12px", "lineHeight": "2"},
        {"color": "red", "fontSize": "12px"},
        {"color": "red"},
    ]


def test_another_mark_between_the_spans_does_not_stop_inheritance():
    assert runs('<span color="red">a <u>b <span fontSize="12px">c</span></u></span>')[-1] == (
        "c", {"textStyle": {"color": "red", "fontSize": "12px"}, "underline": {}},
    )


def test_a_span_that_is_not_nested_inherits_nothing():
    assert runs('<span color="red">a</span> <span fontSize="12px">b</span>')[-1] == (
        "b", {"textStyle": {"fontSize": "12px"}},
    )


def test_an_open_nested_span_inherits_under_partial():
    assert runs('<span color="red">a <span fontSize="12px">b', partial=True)[-1] == (
        "b", {"textStyle": {"color": "red", "fontSize": "12px"}},
    )


def test_merged_styles_are_written_flat_and_read_back_the_same():
    document = tm.from_markdown('<span color="red">a <span fontSize="12px">b</span> c</span>', schema=SCHEMA)
    written = document.to_markdown(canonical=True)

    assert written == '<span color="red">a </span><span color="red" fontSize="12px">b</span><span color="red"> c</span>'
    assert tm.from_markdown(written, schema=SCHEMA).to_dict() == document.to_dict()


def test_only_attrs_declared_to_inherit_are_taken_from_the_outer_mark():
    styled = tm.MarkSpec("styled", tag="span", attrs={
        "color": tm.Attr(str, inherit=True),
        "comment": tm.Attr(str),
    })
    schema = tm.Schema(marks=[styled])

    assert runs('<span color="red" comment="c1">a <span comment="c2">b</span> <span>c</span></span>', schema) == [
        ("a ", {"styled": {"color": "red", "comment": "c1"}}),
        ("b", {"styled": {"color": "red", "comment": "c2"}}),
        (" ", {"styled": {"color": "red", "comment": "c1"}}),
        ("c", {"styled": {"color": "red"}}),
    ]


def test_writing_the_declared_default_still_overrides_the_outer_value():
    styled = tm.MarkSpec("styled", tag="span", attrs={"color": tm.Attr(str, default="black", inherit=True)})
    schema = tm.Schema(marks=[styled])

    assert runs('<span color="red">a <span color="black">b</span></span>', schema) == [
        ("a ", {"styled": {"color": "red"}}),
        ("b", {"styled": {}}),
    ]


def test_text_style_can_turn_the_merge_off_as_the_editor_option_does():
    schema = tm.Schema(marks=[tm.text_style(merge_nested_span_styles=False)])

    assert runs('<span color="red">a <span fontSize="12px">b</span></span>', schema)[-1] == (
        "b", {"textStyle": {"fontSize": "12px"}},
    )


def test_the_text_style_preset_inherits_every_attr_and_highlight_none():
    assert all(attr.inherit for attr in tm.TEXT_STYLE.attrs.values())
    assert not any(attr.inherit for attr in tm.text_style(merge_nested_span_styles=False).attrs.values())
    assert not any(attr.inherit for attr in tm.HIGHLIGHT.attrs.values())


def test_marks_that_stack_do_not_inherit():
    stacking = tm.MarkSpec("tint", tag="span", attrs={
        "color": tm.Attr(str, inherit=True), "size": tm.Attr(str, inherit=True),
    }, excludes=())
    paragraph = tm.from_markdown('<span color="red">a <span size="2">b</span></span>',
                                 schema=tm.Schema(marks=[stacking])).to_dict()["content"][0]

    assert [mark["attrs"] for mark in paragraph["content"][1]["marks"]] == [{"color": "red"}, {"size": "2"}]


def test_inherit_survives_the_schema_dict_and_takes_part_in_equality_and_the_fingerprint():
    plain = tm.Schema(marks=[tm.MarkSpec("styled", tag="span", attrs={"color": tm.Attr(str)})])
    inheriting = tm.Schema(marks=[tm.MarkSpec("styled", tag="span", attrs={"color": tm.Attr(str, inherit=True)})])

    assert inheriting.to_dict()["marks"][0]["attrs"]["color"]["inherit"] is True
    assert plain.to_dict()["marks"][0]["attrs"]["color"]["inherit"] is False
    assert tm.Schema.from_dict(inheriting.to_dict()) == inheriting
    assert plain != inheriting
    fingerprint = lambda schema: tm.from_markdown("x", schema=schema).dump()["schema"]
    assert fingerprint(plain) != fingerprint(inheriting)
    assert fingerprint(tm.Schema.from_dict(inheriting.to_dict())) == fingerprint(inheriting)


def test_a_schema_dict_without_the_key_does_not_inherit():
    declaration = {"marks": [{"name": "styled", "tag": "span", "attrs": {"color": {"type": "str"}}}]}

    assert tm.Schema.from_dict(declaration).marks[0].attrs["color"].inherit is False


@pytest.mark.parametrize("declare", [
    lambda attr: tm.Schema(nodes=[tm.NodeSpec("callout", "block", content="block+", attrs={"tone": attr})]),
    lambda attr: tm.Schema(core_attrs={"paragraph": {"tone": attr}}),
])
def test_only_a_declared_mark_attr_can_inherit(declare):
    with pytest.raises(ValueError, match="cannot inherit"):
        declare(tm.Attr(str, inherit=True))


def test_inherit_must_be_a_bool():
    with pytest.raises(TypeError, match="inherit must be a bool"):
        tm.Schema(marks=[tm.MarkSpec("styled", tag="span", attrs={"color": tm.Attr(str, inherit=1)})])
