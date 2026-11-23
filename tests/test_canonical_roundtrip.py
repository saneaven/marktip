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
            code = ("code", ()) in marks
            for char, category in _non_whitespace(node["text"]):
                value = ("code", char) if code else char
                yield (), value, marks if code or category[0] not in "PS" else frozenset()
        elif kind == "codeBlock":
            body = "".join(char for child in children for char, _ in _non_whitespace(child["text"]))
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
                if child["type"] == "htmlInline":
                    return marks | frozenset(mark_key(mark) for mark in child.get("marks", ()))
                return index

            positions = Counter()
            for group_marks, group in groupby(enumerate(children), key=child_group):
                index, child = next(group)
                child_kind = child["type"]
                child_attrs = child.get("attrs", {})
                if child_kind == "htmlInline":
                    html = child_attrs["html"] + "".join(part["attrs"]["html"] for _, part in group)
                    characters = (((), (child_kind, html), group_marks),)
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


def _run_ids(variant, masks):
    return [f"{variant}-{mask}" for mask in masks.split()]


class _CanonicalMismatch(AssertionError):
    pass


class _BaseSpellingMismatch(AssertionError):
    pass


RUN_MASKS = tuple("".join(str(mask) for mask in masks) for masks in product(range(8), repeat=3))

# Keep the failing case IDs fixed so each completed plan item exposes its XPASSes.
XFAIL_GROUPS = (
    ("M3 normalizes emphasis boundaries that lose whitespace or punctuation",
     ["markdown-html-true-commonmark-430", "markdown-html-false-commonmark-430", "editor-commonmark-430",
      "strike-trailing-space", "italic-space-after-bold-letter", "bold-quoted-letter-between-letters",
      "bold-colon-before-word", "emphasis-on-hard-break"] + _run_ids("latin-spaced", """
         010 012 014 016 020 021 024 025 030 031 032 034 035 036 040 041 042 043
         050 051 052 053 054 056 060 061 062 063 064 065 070 071 072 073 074 075
         076 100 101 102 103 104 105 106 107 110 112 114 116 120 121 122 123 124
         125 126 127 130 131 132 134 135 136 140 141 142 143 144 145 146 147 150
         151 152 153 154 156 160 161 162 163 164 165 166 167 170 171 172 173 174
         175 176 200 201 202 203 204 205 206 207 210 211 212 213 214 215 216 217
         220 221 224 225 230 231 232 234 235 236 240 241 242 243 244 245 246 247
         250 251 252 253 254 255 256 257 260 261 262 263 264 265 270 271 272 273
         274 275 276 300 301 302 303 304 305 306 307 310 311 312 313 314 315 316
         317 320 321 322 323 324 325 326 327 330 331 332 334 335 336 340 341 342
         343 344 345 346 347 350 351 352 353 354 355 356 357 360 361 362 363 364
         365 366 367 370 371 372 373 374 375 376 400 401 402 403 404 405 406 407
         410 411 412 413 414 415 416 417 420 421 422 423 424 425 426 427 430 431
         432 433 434 435 436 437 440 441 442 443 450 451 452 453 454 456 460 461
         462 463 464 465 470 471 472 473 474 475 476 500 501 502 503 504 505 506
         507 510 511 512 513 514 515 516 517 520 521 522 523 524 525 526 527 530
         531 532 533 534 535 536 537 540 541 542 543 544 545 546 547 550 551 552
         553 554 556 560 561 562 563 564 565 566 567 570 571 572 573 574 575 576
         600 601 602 603 604 605 606 607 610 611 612 613 614 615 616 617 620 621
         622 623 624 625 626 627 630 631 632 633 634 635 636 637 640 641 642 643
         644 645 646 647 650 651 652 653 654 655 656 657 660 661 662 663 664 665
         670 671 672 673 674 675 676 700 701 702 703 704 705 706 707 710 711 712
         713 714 715 716 717 720 721 722 723 724 725 726 727 730 731 732 733 734
         735 736 737 740 741 742 743 744 745 746 747 750 751 752 753 754 755 756
         757 760 761 762 763 764 765 766 767 770 771 772 773 774 775 776
     """)),
    ("E1 rejects touching emphasis that loses marks or becomes literal punctuation",
     ["touching-strike-inside-italic", "touching-crossed-bold-and-italic"], pytest.raises.Exception),
    # Masks use bold=1, italic=2 and strike=4 in run order.
    ("E1 rejects touching emphasis that drops marks or produces literal delimiters",
     _run_ids("latin-touching", """
         005 006 007 017 027 035 050 051 052 053 054 055 056 057 060 061 062 063
         064 065 066 067 070 071 072 073 074 075 076 077 105 106 107 117 123 127
         132 136 150 152 160 170 171 172 173 174 175 176 177 205 206 207 213 217
         227 231 235 250 260 261 270 271 272 273 274 275 276 277 305 306 307 317
         323 327 335 350 351 352 353 354 355 356 357 360 361 367 370 371 372 405
         406 407 417 427 435 450 460 470 500 501 502 503 504 505 506 507 517 527
         536 550 560 567 570 576 600 601 602 603 604 605 606 607 617 627 635 650
         657 660 670 675 700 701 702 703 704 705 706 707 717 727 735 750 760 767
         770
     """)),
    ("cjk_friendly (step 6) adds the required reading option to from_dict",
     [f"hangul-touching-{masks}" for masks in RUN_MASKS], TypeError),
)
XFAIL = {
    case_id: pytest.mark.xfail(strict=True, reason=reason, raises=tuple(errors) or _CanonicalMismatch)
    for reason, case_ids, *errors in XFAIL_GROUPS
    for case_id in case_ids
}


def _case(case_id, *args):
    return pytest.param(*args, id=case_id, marks=XFAIL.get(case_id, ()))


def _canonical_roundtrip(document, **options):
    canonical = document.to_markdown(canonical=True)
    reread = tm.from_markdown(canonical, **options)
    rewritten = reread.to_markdown(canonical=True)
    if not (reread == document and rewritten == canonical):
        raise _CanonicalMismatch(canonical, rewritten, document.to_dict(), reread.to_dict())
    return canonical


def _base_spelling(document, markdown):
    written = document.to_markdown()
    if written != markdown:
        raise _BaseSpellingMismatch(markdown, written)


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
        _case(f"markdown-html-{str(html).lower()}-{example.id}", example.values[0], html)
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


@pytest.mark.parametrize(
    "markdown",
    [_case(f"editor-{example.id}", example.values[0]) for example in EXAMPLES],
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
    [_case(case_id, x, dict_options, markdown_options, refuses, normalized, expected_markdown)
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
    )
    for variant, letters, options in runs:
        for masks in RUN_MASKS:
            content = [{"type": "text", "text": letter, "marks": mark_sets[int(mask)]}
                       for letter, mask in zip(letters, masks)]
            x = {"type": "doc", "content": [{"type": "paragraph", "content": content}]}
            yield _case(f"{variant}-{masks}", x, options, variant != "latin-spaced")


@pytest.mark.parametrize("x,options,allow_refusal", list(_three_run_documents()))
def test_canonical_from_three_runs(x, options, allow_refusal):
    try:
        document = tm.from_dict(x, strict="content", **options)
    except tm.InvalidNodeError as error:
        if not allow_refusal:
            raise
        assert error.code == "unrepresentable"
        return

    _editor_invariants(x, document, options)
    _canonical_roundtrip(document, **options)
