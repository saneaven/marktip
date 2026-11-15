"""Declared content expressions accept complete ordered child sequences."""

from itertools import product
import re

import pytest

import marktip as tm


CONTAINER_PATH = "content[0].content[0]"
EXPRESSIONS = (
    ("first", "F"),
    ("first second", "FS"),
    ("second first", "SF"),
    ("first | second", "F|S"),
    ("first | second second", "F|SS"),
    ("(first | second) second", "(F|S)S"),
    ("first*", "F*"),
    ("first* | second", "F*|S"),
    ("first{0,} | second", "F*|S"),
    ("(first* second)+", "(F*S)+"),
    ("(first{0,} second)+", "(F*S)+"),
    ("(first* second)*", "(F*S)*"),
    ("(first{0,} second)*", "(F*S)*"),
    ("first+", "F+"),
    ("first?", "F?"),
    ("first{0}", ""),
    ("first{2}", "F{2}"),
    ("first{2,}", "F{2,}"),
    ("first{1,3}", "F{1,3}"),
    ("(first second){1,2}", "(FS){1,2}"),
    ("first? second+", "FS+|S+"),
    ("(first | second)* first second?", "(F|S)*FS?"),
    ("((first second)? first)+", "((FS)?F)+"),
    ("(first{0} | second)*", "S*"),
    ("(first? second?)+", "(F?S?)+"),
    ("first**", "F*"),
    ("(first+)?", "(F+)?"),
    ("first{3,2}", "F{3}"),
    ("tokens*", "(F|S)*"),
    ("tokens{1,3}", "(F|S){1,3}"),
    ("firsts seconds?", "FS?"),
    ("  first  (seconds | firsts)?  ", "F(S|F)?"),
)


def schema_for(expression):
    return tm.Schema(nodes=[
        tm.NodeSpec("wrap", kind="inline", content=expression),
        tm.NodeSpec("first", kind="inline", group="tokens firsts"),
        tm.NodeSpec("second", kind="inline", group="tokens seconds"),
    ])


def document(sequence, *, empty_content=True):
    container = {"type": "wrap"}
    if sequence or empty_content:
        container["content"] = [{"type": "first" if symbol == "F" else "second"} for symbol in sequence]
    return {"type": "doc", "content": [{"type": "paragraph", "content": [container]}]}


def assert_invalid_content(ast, schema, level):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, schema=schema, strict=level)
    assert excinfo.value.code == "invalid_content"
    assert excinfo.value.field == "content"
    assert excinfo.value.path == CONTAINER_PATH


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("expression, pattern", EXPRESSIONS)
def test_content_expression_matches_an_independent_regular_expression(level, expression, pattern):
    schema = schema_for(expression)
    oracle = re.compile(pattern)
    for length in range(6):
        for sequence in product("FS", repeat=length):
            accepted = oracle.fullmatch("".join(sequence)) is not None
            ast = document(sequence)
            if accepted:
                result = tm.from_dict(ast, schema=schema, strict=level).to_dict()
                assert result == document(sequence, empty_content=False)
            else:
                assert_invalid_content(ast, schema, level)

    missing_content = document((), empty_content=False)
    if oracle.fullmatch("") is not None:
        assert tm.from_dict(missing_content, schema=schema, strict=level).to_dict() == missing_content
    else:
        assert_invalid_content(missing_content, schema, level)


@pytest.mark.parametrize("level", ("content", "exact"))
def test_none_and_empty_content_declare_atoms(level):
    for expression in (None, ""):
        schema = schema_for(expression)
        ast = document((), empty_content=False)
        parsed = tm.from_dict(ast, schema=schema, strict=level)
        assert parsed.to_dict() == ast
        assert parsed.to_markdown(canonical=True) == "<wrap/>"
        assert_invalid_content(document(()), schema, level)
        assert_invalid_content(document(("F",)), schema, level)


@pytest.mark.parametrize("level", ("content", "exact"))
def test_node_name_takes_priority_over_a_group_with_the_same_name(level):
    schema = tm.Schema(nodes=[
        tm.NodeSpec("wrap", kind="inline", content="first"),
        tm.NodeSpec("first", kind="inline"),
        tm.NodeSpec("second", kind="inline", group="first"),
    ])
    ast = document(("F",))
    assert tm.from_dict(ast, schema=schema, strict=level).to_dict() == ast
    assert_invalid_content(document(("S",)), schema, level)


@pytest.mark.parametrize("level", ("content", "exact"))
@pytest.mark.parametrize("whitespace", (
    " ", "\t", "\n", "\v", "\f", "\r", "\u00a0", "\u1680",
    *(chr(codepoint) for codepoint in range(0x2000, 0x200B)),
    "\u2028", "\u2029", "\u202f", "\u205f", "\u3000", "\ufeff",
))
def test_javascript_whitespace_separates_content_expression_tokens(level, whitespace):
    expressions = (
        (f"first{whitespace}second", "FS"),
        (f"({whitespace}first{whitespace}|{whitespace}second{whitespace}){whitespace}*", "(F|S)*"),
        (f"first{whitespace}+{whitespace}second{whitespace}?", "F+S?"),
        (f"first{whitespace}{{{whitespace}1{whitespace},{whitespace}2{whitespace}}}"
         f"{whitespace}second{whitespace}{{{whitespace}0{whitespace},{whitespace}}}", "F{1,2}S*"),
    )
    for expression, pattern in expressions:
        schema = schema_for(whitespace + expression + whitespace)
        oracle = re.compile(pattern)
        for length in range(4):
            for sequence in product("FS", repeat=length):
                ast = document(sequence)
                if oracle.fullmatch("".join(sequence)) is not None:
                    result = tm.from_dict(ast, schema=schema, strict=level).to_dict()
                    assert result == document(sequence, empty_content=False)
                else:
                    assert_invalid_content(ast, schema, level)


def assert_adjacent_count_rejected(expression):
    with pytest.raises(ValueError) as excinfo:
        schema_for(expression)
    message = str(excinfo.value)
    assert "must not depend on how many adjacent text nodes there are" in message
    assert "text*" in message
    assert "text+" in message


@pytest.mark.parametrize("symbol", ("text", "htmlInline"))
@pytest.mark.parametrize("pattern", (
    "{symbol}*", "{symbol}+", "({symbol} | first)*", "{symbol}{{1,}}",
    "first {symbol}*", "{symbol}+ first {symbol}+", "({symbol}{{2}}){{0}}",
))
def test_adjacent_text_count_invariant_is_a_property_of_the_compiled_dfa(symbol, pattern):
    assert schema_for(pattern.format(symbol=symbol))


@pytest.mark.parametrize("symbol", ("text", "htmlInline"))
@pytest.mark.parametrize("pattern", (
    "{symbol}", "{symbol}?", "{symbol}{{2}}", "{symbol}{{2,}}",
    "{symbol} first", "first {symbol}", "first {symbol}{{2,}}",
))
def test_content_expression_cannot_distinguish_one_text_node_from_an_adjacent_run(symbol, pattern):
    assert_adjacent_count_rejected(pattern.format(symbol=symbol))


@pytest.mark.parametrize("expression", ("inline", "inline?", "inline{2,}", "first inline"))
def test_group_resolution_cannot_hide_an_adjacent_text_count(expression):
    assert_adjacent_count_rejected(expression)


@pytest.mark.parametrize("expression", ("text*", "text+", "(text | mention)*"))
def test_text_run_expressions_from_decision_16_are_accepted(expression):
    assert tm.Schema(nodes=[tm.NodeSpec("pair", kind="inline", content=expression),
                            tm.NodeSpec("mention", kind="inline")])


@pytest.mark.parametrize("expression", ("text", "text?", "text{2}", "text{2,}", "text mention"))
def test_text_count_expressions_from_decision_16_are_rejected(expression):
    with pytest.raises(ValueError, match="use text\\* or text\\+"):
        tm.Schema(nodes=[tm.NodeSpec("pair", kind="inline", content=expression),
                         tm.NodeSpec("mention", kind="inline")])


def test_schema_rejects_the_adjacent_text_merge_roundtrip_repro():
    # Equal-mark neighbors write as one text run: <pair>ab</pair>.
    with pytest.raises(ValueError, match="how many adjacent text nodes"):
        tm.Schema(nodes=[tm.NodeSpec("pair", kind="inline", content="text{2}")])


def test_schema_rejects_the_boundary_whitespace_split_roundtrip_repro():
    # Expelling boundary whitespace from bold " x " creates three text nodes.
    with pytest.raises(ValueError, match="how many adjacent text nodes"):
        tm.Schema(nodes=[tm.NodeSpec("pair", kind="inline", content="text")])
