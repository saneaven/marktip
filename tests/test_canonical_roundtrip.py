from collections import Counter
from itertools import groupby, product
import unicodedata

import pytest

import marktip as tm

from editor_documents import EDITOR_DOCUMENTS
from spec_examples import EXAMPLES, editor_dict


def _value(value):
    if isinstance(value, dict):
        return tuple(value.items())
    if isinstance(value, list):
        return tuple(value)
    return value


def _non_whitespace(text):
    for char in text:
        category = unicodedata.category(char)
        if category != "Zs" and char not in "\t\n\f\r":
            yield char, category


def _normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _signature(document, schema):
    declarations = {} if schema is None else {mark.name: mark.attrs for mark in schema.marks}
    overlays = {} if schema is None else schema.core_attrs
    math_bodies = {} if schema is None else {node.name: node.body for node in schema.nodes if node.math}

    def mark_key(mark):
        kind = mark["type"]
        attrs = mark.get("attrs", {})
        declared = declarations.get(kind, overlays.get(kind, {}))
        carried = []
        for key, spec in declared.items():
            value = attrs.get(key)
            if value is not None and value != spec.default and value != {}:
                carried.append((key, _value(value)))
        if kind == "link":
            carried.append(("href", attrs["href"]))
        return kind, tuple(sorted(carried))

    def visits(node, inherited):
        kind = node["type"]
        marks = inherited | frozenset(mark_key(mark) for mark in node.get("marks", ()))
        attrs = node.get("attrs", {})
        children = node.get("content", ())
        if kind == "text":
            for char, category in _non_whitespace(node["text"]):
                yield (), char, marks if category[0] not in "PS" else frozenset()
        elif kind == "codeBlock":
            # The reader already removes the code block's structural newline.
            body = _normalize_newlines("".join(child["text"] for child in children))
            yield (), (kind, body), marks
        elif kind == "image":
            yield (), (kind, attrs["src"], attrs.get("alt") or "", attrs.get("title") or ""), marks
        elif kind in ("htmlBlock", "htmlInline"):
            yield (), (kind, attrs["html"]), marks
        elif kind in math_bodies:
            yield (), (kind, attrs[math_bodies[kind]]), marks
        else:
            def child_group(entry):
                index, child = entry
                child_kind = child["type"]
                if child_kind in ("htmlInline", "text"):
                    child_marks = marks | frozenset(mark_key(mark) for mark in child.get("marks", ()))
                    if child_kind == "htmlInline" or ("code", ()) in child_marks:
                        return child_kind, child_marks
                return index, None

            positions = Counter()
            for (group_kind, group_marks), group in groupby(enumerate(children), key=child_group):
                index, child = next(group)
                child_kind = child["type"]
                child_attrs = child.get("attrs", {})
                if group_kind == "htmlInline":
                    html = child_attrs["html"] + "".join(part["attrs"]["html"] for _, part in group)
                    characters = (((), (child_kind, html), group_marks),)
                elif group_kind == "text":
                    # Adjacent equal-mark runs can split a CRLF across nodes.
                    body = child["text"] + "".join(part["text"] for _, part in group)
                    for char in _normalize_newlines(body).replace("\n", " "):
                        yield (), ("code", char), group_marks
                    continue
                else:
                    characters = tuple(visits(child, marks))
                if child_kind == "text":
                    yield from characters
                    continue

                label = child_kind
                detail = ()
                if child_kind in ("tableHeader", "tableCell"):
                    label = "tableCell"
                elif child_kind in ("bulletList", "orderedList", "taskList"):
                    label, detail = "list", (child_kind,)
                elif child_kind in ("listItem", "taskItem"):
                    label = "item"
                    if child_kind == "taskItem":
                        detail = (child_attrs.get("checked", False),)
                elif child_kind == "heading":
                    detail = (child_attrs.get("level", 1),)

                if child_kind == "paragraph" and kind in ("tableHeader", "tableCell"):
                    component = (label,)
                elif child_kind in ("listItem", "taskItem", "tableRow", "tableHeader", "tableCell"):
                    component = (label, index, *detail)
                else:
                    if not characters and (
                        child_kind == "paragraph" or (label in ("list", "table") and not child.get("content"))
                    ):
                        continue
                    component = (label, positions[label], *detail)
                    positions[label] += 1
                for path, char, char_marks in characters:
                    yield (component, *path), char, char_marks

    return tuple(visits(document, frozenset()))


RUN_MASKS = tuple("".join(str(mask) for mask in masks) for masks in product(range(8), repeat=3))

# Masks use bold=1, italic=2 and strike=4 in run order.
# These cases fail with the writer's one spelling.
# Some have another spelling that marktip does not search for.
PUNCTUATION_REFUSALS = "123 127 132 136 213 217 231 235 323 327 363 367 567 576 657 675 767".split()
REFUSES = {
    "latin-touching": """
        005 006 007 017 027 035 050 051 052 053 054 055 056 057 060 061 062 063
        064 065 066 067 070 071 072 073 074 075 076 077 105 106 107 117 123 127
        132 136 150 152 160 170 171 172 173 174 175 176 177 205 206 207 213 217
        227 231 235 250 260 261 270 271 272 273 274 275 276 277 305 306 307 317
        323 327 335 350 351 352 353 354 355 356 357 360 361 367 370 371 372 405
        406 407 417 427 435 450 460 470 500 501 502 503 504 505 506 507 517 527
        536 550 560 567 570 576 600 601 602 603 604 605 606 607 617 627 635 650
        657 660 670 675 700 701 702 703 704 705 706 707 717 727 735 750 760 767
        770
    """.split(),
    "hangul-touching": """
        123 127 132 136 213 217 231 235 323 327 363 367 567 576 657 675 767
    """.split(),
    "latin-quoted": PUNCTUATION_REFUSALS,
    "latin-punctuated": PUNCTUATION_REFUSALS,
    "hangul-punctuated": PUNCTUATION_REFUSALS,
}


def _canonical_roundtrip(document, **options):
    canonical = document.to_markdown(canonical=True)
    reread = tm.from_markdown(canonical, **options)
    assert reread == document, (canonical, document.to_dict(), reread.to_dict())
    assert reread.to_markdown(canonical=True) == canonical
    return canonical


def _base_spelling(document, markdown):
    assert document.to_markdown() == markdown


def _storage_roundtrip(document, **options):
    assert tm.from_dict(document.to_dict(), strict="content", **options) == document
    assert tm.load(document.dump(), schema=options.get("schema")) == document


def _editor_invariants(x, document, dict_options):
    schema = dict_options.get("schema")
    assert _signature(x, schema) == _signature(document.to_dict(), schema)
    _storage_roundtrip(document, **{key: value for key, value in dict_options.items() if key != "base"})


@pytest.mark.parametrize(
    "markdown,html",
    [
        pytest.param(example.values[0], html, id=f"markdown-html-{str(html).lower()}-{example.id}")
        for html in (True, False)
        for example in EXAMPLES
    ],
)
def test_canonical_from_markdown(markdown, html):
    document = tm.from_markdown(markdown, html=html)
    _storage_roundtrip(document)
    _canonical_roundtrip(document, html=html)


def test_canonical_from_markdown_joins_adjacent_equal_mark_html():
    document = tm.from_markdown("[**<b>**](u)**[</b>](u)**")
    assert document == tm.from_markdown("[**<b></b>**](u)")
    _storage_roundtrip(document)
    _canonical_roundtrip(document)


@pytest.mark.parametrize("ending,options", [("\n", {}), (".\ufe00", {"cjk_friendly": True})])
def test_emphasis_closes_before_a_line_end_or_variation_sequence(ending, options):
    ast = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "x" + ending, "marks": [{"type": "bold"}]},
        {"type": "text", "text": "c"},
    ]}]}
    document = tm.from_dict(ast, strict="content", **options)
    assert _canonical_roundtrip(document, **options) == f"**x**{ending}c"


def test_emphasis_opens_on_punctuation_after_a_line_end():
    ast = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "a\n"},
        {"type": "text", "text": '"b"', "marks": [{"type": "bold"}]},
    ]}]}
    document = tm.from_dict(ast, strict="content")
    assert document.to_dict() == ast
    assert _canonical_roundtrip(document) == 'a\n**"b"**'


@pytest.mark.parametrize(
    "markdown",
    [pytest.param(example.values[0], id=f"editor-{example.id}") for example in EXAMPLES],
)
def test_canonical_from_editor_spec(markdown):
    base = tm.from_markdown(markdown)
    x = editor_dict(base.to_dict(), fill_empty=True, add_colspan=False)
    document = tm.from_dict(x, strict="content")
    _editor_invariants(x, document, {})
    _base_spelling(tm.from_dict(x, strict="content", base=base), markdown)
    _canonical_roundtrip(document)


@pytest.mark.parametrize(
    "x,dict_options,markdown_options,refuses,normalized,expected_markdown",
    [pytest.param(x, dict_options, markdown_options, refuses, normalized, expected_markdown, id=case_id)
     for case_id, x, dict_options, markdown_options, refuses, normalized, expected_markdown in EDITOR_DOCUMENTS],
)
def test_canonical_from_editor_document(x, dict_options, markdown_options, refuses, normalized, expected_markdown):
    if refuses:
        with pytest.raises(tm.InvalidNodeError) as error:
            tm.from_dict(x, strict="content", **dict_options)
        assert error.value.code == "unrepresentable"
        return

    document = tm.from_dict(x, strict="content", **dict_options)
    _editor_invariants(x, document, dict_options)
    if "base" in dict_options:
        _base_spelling(document, dict_options["base"].to_markdown())
    canonical = _canonical_roundtrip(document, **markdown_options)
    if normalized is not None:
        assert document.to_dict() == normalized
    if expected_markdown is not None:
        assert canonical == expected_markdown


def _three_run_documents():
    mark_names = ("bold", "italic", "strike")
    mark_sets = [[{"type": name} for bit, name in enumerate(mark_names) if mask & (1 << bit)]
                 for mask in range(8)]
    runs = (
        ("latin-spaced", ("a ", "b ", "c"), {}),
        ("latin-touching", ("a", "b", "c"), {}),
        ("hangul-touching", ("가", "나", "다"), {"cjk_friendly": True}),
        ("latin-quoted", ('"a"', '"b"', '"c"'), {}),
        ("latin-punctuated", ("a.", ".b.", ".c"), {}),
        ("hangul-punctuated", ("가.", ".나.", ".다"), {"cjk_friendly": True}),
    )
    for variant, letters, options in runs:
        for masks in RUN_MASKS:
            content = [{"type": "text", "text": letter, "marks": mark_sets[int(mask)]}
                       for letter, mask in zip(letters, masks)]
            x = {"type": "doc", "content": [{"type": "paragraph", "content": content}]}
            refuses = masks in REFUSES.get(variant, ())
            yield pytest.param(x, options, refuses, id=f"{variant}-{masks}")


@pytest.mark.parametrize("x,options,refuses", list(_three_run_documents()))
def test_canonical_from_three_runs(x, options, refuses):
    if refuses:
        with pytest.raises(tm.InvalidNodeError) as error:
            tm.from_dict(x, strict="content", **options)
        assert error.value.code == "unrepresentable"
        permissive = tm.from_dict(x, strict="off", **options)
        assert _signature(x, None) == _signature(permissive.to_dict(), None)
        assert tm.from_markdown(permissive.to_markdown(canonical=True), **options) != permissive
        return

    document = tm.from_dict(x, strict="content", **options)
    _editor_invariants(x, document, options)
    _canonical_roundtrip(document, **options)
