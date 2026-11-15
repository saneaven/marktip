"""Inline shapes and child-set membership have separate validation rules."""

import pytest

import marktip as tm


LEVELS = ("off", "content", "exact")
STRICT_LEVELS = ("content", "exact")
NODE_PATH = "content[0].content[0]"


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def p(*children):
    return {"type": "paragraph", "content": list(children)}


def text(value="x", *marks):
    out = {"type": "text", "text": value}
    if marks:
        out["marks"] = list(marks)
    return out


def atom_schema(**attrs):
    return tm.Schema(nodes=[tm.NodeSpec("mention", kind="inline", attrs=attrs)])


def invalid(ast, schema, level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    return excinfo.value


@pytest.mark.parametrize("level", LEVELS)
def test_default_inline_group_accepts_atoms_with_ordinary_marks(level):
    schema = atom_schema(id=tm.Attr(str, required=True))
    mention = {"type": "mention", "attrs": {"id": "u1"}, "marks": [{"type": "bold"}]}
    assert tm.from_dict(doc(p(mention)), schema=schema, strict=level).to_dict() == doc(p(mention))


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("group", ("tokens", ""))
def test_explicit_group_replaces_inline_membership_but_atoms_can_still_have_marks(level, group):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("mention", kind="inline", group=group),
        tm.NodeSpec("holder", kind="inline", content="tokens+" if group else "mention+"),
    ])
    mention = {"type": "mention", "marks": [{"type": "bold"}]}
    ast = doc(p({"type": "holder", "content": [mention]}))
    assert tm.from_dict(ast, schema=schema, strict=level).to_dict() == ast
    err = invalid(doc(p(mention)), schema, level)
    assert err.code == "invalid_content"
    assert err.field == "content"
    assert err.path == NODE_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("marks", ([], None, [{"type": "bold"}], [{"type": "code"}]))
def test_inline_containers_refuse_the_marks_field(level, marks):
    schema = tm.Schema(nodes=[tm.NodeSpec("ruby", kind="inline", content="text*")])
    err = invalid(doc(p({"type": "ruby", "marks": marks})), schema, level)
    assert err.code == "unknown_field"
    assert err.field == "marks"
    assert err.path == NODE_PATH
    assert str(err) == "field 'marks' is not defined for node type 'ruby'"


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_code_mark_on_a_declared_atom_is_an_invalid_mark_set(level):
    mention = {"type": "mention", "marks": [{"type": "bold"}, {"type": "code"}]}
    err = invalid(doc(p(mention)), atom_schema(), level)
    assert err.code == "invalid_mark_set"
    assert err.field == "marks"
    assert err.path == NODE_PATH


def test_off_stores_atom_code_marks_but_the_writer_drops_them():
    mention = {"type": "mention", "marks": [{"type": "code"}]}
    document = tm.from_dict(doc(p(mention)), schema=atom_schema(), strict="off")
    assert document.to_dict() == doc(p(mention))
    assert document.to_markdown(canonical=True) == "<mention/>"


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_declared_atoms_refuse_even_an_empty_content_field(level):
    err = invalid(doc(p({"type": "mention", "content": []})), atom_schema(), level)
    assert err.code == "invalid_content"
    assert err.field == "content"
    assert err.path == NODE_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("content", (None, []))
def test_required_container_content_is_checked_when_missing_or_empty(level, content):
    schema = tm.Schema(nodes=[tm.NodeSpec("ruby", kind="inline", content="text+")])
    ruby = {"type": "ruby"}
    if content is not None:
        ruby["content"] = content
    err = invalid(doc(p(ruby)), schema, level)
    assert err.code == "invalid_content"
    assert err.field == "content"
    assert err.path == NODE_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("content", (None, []))
def test_optional_container_content_accepts_missing_and_empty_sequences(level, content):
    schema = tm.Schema(nodes=[tm.NodeSpec("ruby", kind="inline", content="text*")])
    ruby = {"type": "ruby"}
    if content is not None:
        ruby["content"] = content
    assert tm.from_dict(doc(p(ruby)), schema=schema, strict=level).to_dict() == doc(p({"type": "ruby"}))


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_full_child_sequence_checks_order_and_multiplicity(level):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("mention", kind="inline"),
        tm.NodeSpec("ruby", kind="inline", content="text+ mention{1,2} text*"),
    ])
    mention = {"type": "mention"}
    for children in ([text(), mention], [text(), mention, mention, text("end")]):
        ast = doc(p({"type": "ruby", "content": children}))
        assert tm.from_dict(ast, schema=schema, strict=level).to_dict() == ast
    for children in ([text()], [mention, text()], [text(), mention, mention, mention]):
        err = invalid(doc(p({"type": "ruby", "content": children})), schema, level)
        assert err.code == "invalid_content"
        assert err.field == "content"
        assert err.path == NODE_PATH


def test_off_skips_the_declared_content_expression():
    schema = tm.Schema(nodes=[tm.NodeSpec("ruby", kind="inline", content="text+")])
    ast = doc(p({"type": "ruby"}))
    assert tm.from_dict(ast, schema=schema, strict="off").to_dict() == ast


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_core_code_block_rules_still_apply_with_declared_nodes(level):
    schema = atom_schema()
    err = invalid(doc({"type": "codeBlock", "content": [{"type": "mention"}]}), schema, level)
    assert err.code == "invalid_content"
    assert err.field == "content"
    assert err.path == "content[0].content[0]"
    err = invalid(doc({"type": "codeBlock", "content": [text("x", {"type": "code"})]}), schema, level)
    assert err.code == "invalid_content"
    assert err.field == "marks"
    assert err.path == "content[0].content[0]"


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("type_", ("paragraph", "listItem", "tableRow"))
def test_core_structural_nodes_do_not_gain_a_marks_field(level, type_):
    err = invalid(doc({"type": type_, "marks": []}), atom_schema(), level)
    assert err.code == "unknown_field"
    assert err.field == "marks"
    assert err.path == "content[0]"


@pytest.mark.parametrize("level", STRICT_LEVELS)
def test_raw_html_that_would_be_a_declared_node_is_unrepresentable(level):
    err = invalid(doc(p({"type": "htmlInline", "attrs": {"html": "<mention/>"}})), atom_schema(), level)
    assert err.code == "unrepresentable"
    assert err.field == "html"
    assert err.path == NODE_PATH


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("uri", ("link", "image"))
def test_declared_node_uris_use_the_matching_policy(level, uri):
    schema = atom_schema(url=tm.Attr(str, uri=uri))
    ast = doc(p({"type": "mention", "attrs": {"url": "https://example.com/x"}}))
    options = {f"{uri}_schemes": ("https",), f"{uri}_relative": "reject"}
    assert tm.from_dict(ast, schema=schema, strict=level, **options).to_dict() == ast
    options[f"{uri}_schemes"] = ("mailto",)
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level, **options)
    assert excinfo.value.code == "disallowed_scheme"
    assert excinfo.value.field == "url"
    assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("uri", ("link", "image"))
def test_declared_node_uris_check_both_stored_and_entity_decoded_values(level, uri):
    schema = atom_schema(url=tm.Attr(str, uri=uri))
    for value, options, code in (
        ("https&colon;//example.com", {f"{uri}_schemes": ("https",), f"{uri}_relative": "reject"},
         "disallowed_relative_url"),
        ("&#106;avascript:x", {f"{uri}_schemes": ("https",)}, "disallowed_scheme"),
        ("https://example.com/\0x", {}, "invalid_uri_char"),
        ("https://example.com/&#9;x", {}, "invalid_uri_char"),
    ):
        ast = doc(p({"type": "mention", "attrs": {"url": value}}))
        with pytest.raises(tm.InvalidNodeError) as excinfo:
            tm.from_dict(ast, schema=schema, strict=level, **options)
        assert excinfo.value.code == code
        assert excinfo.value.field == "url"
        assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("level", LEVELS)
def test_reject_node_types_accepts_declared_node_names(level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(p({"type": "mention"})), schema=atom_schema(), strict=level,
                     reject_node_types=("mention",))
    assert excinfo.value.code == "disallowed_node_type"
    assert excinfo.value.field == "type"
    assert excinfo.value.path == NODE_PATH


@pytest.mark.parametrize("level", STRICT_LEVELS)
@pytest.mark.parametrize("attrs, code, field", (
    ({}, "missing_attr", "id"),
    ({"id": None}, "missing_attr", "id"),
    ({"id": 1}, "invalid_attr_value", "id"),
    ({"id": "u1", "unknown": 1}, "unknown_attr", "unknown"),
))
def test_declared_node_attrs_keep_located_node_errors(level, attrs, code, field):
    err = invalid(doc(p({"type": "mention", "attrs": attrs})), atom_schema(id=tm.Attr(str, required=True)), level)
    assert err.code == code
    assert err.field == field
    assert err.path == NODE_PATH


@pytest.mark.parametrize("level", LEVELS)
def test_declared_node_defaults_are_unset_at_every_level(level):
    schema = atom_schema(tone=tm.Attr(str, choices=("info", "warning"), default="info"))
    for value in (None, "info"):
        document = tm.from_dict(doc(p({"type": "mention", "attrs": {"tone": value}})),
                                schema=schema, strict=level)
        assert document.to_dict() == doc(p({"type": "mention"}))
