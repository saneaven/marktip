"""Strict dict validation uses the same effective fence info as writing and reading."""

import pytest

import marktip as tm


@pytest.fixture
def schema():
    return tm.Schema(nodes=[tm.NodeSpec("equation", "block", fence="math", body="latex",
                                        attrs={"latex": tm.Attr(str)})])


def document(attrs):
    return {"type": "doc", "content": [{"type": "paragraph"}, {
        "type": "codeBlock", "attrs": attrs,
        "content": [{"type": "text", "text": "x\n"}],
    }]}


@pytest.mark.parametrize("strict", ["content", "exact"])
@pytest.mark.parametrize("attrs, field, info", [
    ({"language": "math"}, "language", "math"),
    ({"info": "math"}, "info", "math"),
    ({"info": "math numbered"}, "info", "math numbered"),
    ({"language": "math", "info": "python"}, "language", "math"),
    ({"language": "", "info": "math"}, "info", "math"),
])
def test_strict_rejects_a_core_code_block_with_a_declared_fence_prefix(schema, strict, attrs, field, info):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(document(attrs), schema=schema, strict=strict)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("unrepresentable", field, "content[1]")
    assert tm.from_dict(document(attrs), schema=schema, strict="off").to_dict() == document({
        "language": "math", "info": info,
    })


@pytest.mark.parametrize("strict", ["content", "exact"])
@pytest.mark.parametrize("attrs, word", [
    ({"language": "python", "info": "math"}, "python"),
    ({"info": "mathematics"}, "mathematics"),
    ({"language": "Math"}, "Math"),
])
def test_fence_collision_matches_the_effective_whole_first_word(schema, strict, attrs, word):
    ast = document(attrs)
    assert tm.from_dict(ast, schema=schema, strict=strict).to_dict() == document({"language": word, "info": word})


@pytest.mark.parametrize("strict", ["content", "exact"])
def test_tab_led_info_stays_a_core_code_block_even_with_a_declared_fence(strict):
    schema = tm.Schema(nodes=[tm.NodeSpec("mermaid", "block", fence="mermaid", body="source",
                                         attrs={"source": tm.Attr(str)})])
    markdown = "```\tmermaid\ngraph\n```"
    ast = {"type": "doc", "content": [{
        "type": "codeBlock", "attrs": {"info": "\tmermaid"},
        "content": [{"type": "text", "text": "graph"}],
    }]}
    assert tm.from_markdown(markdown, schema=schema).to_dict() == ast
    assert tm.from_dict(ast, schema=schema, strict=strict).to_dict() == ast


@pytest.mark.parametrize("carrier, source, path", [
    ("fence", "```math\ny\n```", ""),
    ("inline", "$y$", "content[0]"),
    ("display", "$$y$$", ""),
])
def test_readable_body_uses_the_declared_value_rule(carrier, source, path):
    fields = {"fence": "math"} if carrier == "fence" else {"math": carrier}
    schema = tm.Schema(nodes=[tm.NodeSpec(
        "formula", "inline" if carrier == "inline" else "block", body="latex",
        attrs={"latex": tm.Attr(str, choices=("x",))}, **fields,
    )])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("invalid_attr_value", "latex", path)


@pytest.mark.parametrize("carrier, source, path", [
    ("fence", "```math\nx\n```", ""),
    ("inline", "$x$", "content[0]"),
    ("display", "$$x$$", ""),
])
def test_readable_form_checks_other_required_attrs(carrier, source, path):
    fields = {"fence": "math"} if carrier == "fence" else {"math": carrier}
    schema = tm.Schema(nodes=[tm.NodeSpec(
        "formula", "inline" if carrier == "inline" else "block", body="latex",
        attrs={"latex": tm.Attr(str), "label": tm.Attr(str, required=True)}, **fields,
    )])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(source, schema=schema)
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("missing_attr", "label", path)


@pytest.mark.parametrize("carrier, source", [
    ("fence", "```math\nx\n```"), ("inline", "$x$"), ("display", "$$x$$"),
])
def test_readable_body_elides_the_declared_default(carrier, source):
    fields = {"fence": "math"} if carrier == "fence" else {"math": carrier}
    schema = tm.Schema(nodes=[tm.NodeSpec(
        "formula", "inline" if carrier == "inline" else "block", body="latex",
        attrs={"latex": tm.Attr(str, default="x")}, **fields,
    )])
    parsed = tm.from_markdown(source, schema=schema)
    formula = {"type": "formula"}
    blocks = [{"type": "paragraph", "content": [formula]}] if carrier == "inline" else [formula]
    assert parsed.to_dict() == {"type": "doc", "content": blocks}
    assert parsed.to_markdown(canonical=True) == "<formula/>"


def test_inline_math_body_is_subject_to_the_declared_uri_policy():
    schema = tm.Schema(nodes=[tm.NodeSpec(
        "reference", "inline", math="inline", body="target", attrs={"target": tm.Attr(str, uri="link")},
    )])
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown("$javascript:alert(1)$", schema=schema, link_schemes=("https",))
    error = excinfo.value
    assert (error.code, error.field, error.path) == ("disallowed_scheme", "target", "content[0].content[0]")
