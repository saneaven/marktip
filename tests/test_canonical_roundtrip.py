from collections import Counter
from itertools import product
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
            positions = Counter()
            for index, child in enumerate(children):
                characters = tuple(visits(child, marks))
                child_kind = child["type"]
                child_attrs = child.get("attrs", {})
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


def _spec_ids(prefixes, commonmark="", gfm=""):
    return [f"{prefix}-commonmark-{number}" for prefix in prefixes for number in commonmark.split()] + [
        f"{prefix}-gfm-{number}" for prefix in prefixes for number in gfm.split()
    ]


def _run_ids(variant, masks):
    return [f"{variant}-{mask}" for mask in masks.split()]


class _CanonicalMismatch(AssertionError):
    pass


class _BaseSpellingMismatch(AssertionError):
    pass


MARKDOWN_SPECS = ("markdown-html-true", "markdown-html-false")
EDITOR_SPECS = ("editor",)
ALL_SPECS = (*MARKDOWN_SPECS, *EDITOR_SPECS)
RUN_MASKS = tuple("".join(str(mask) for mask in masks) for masks in product(range(8), repeat=3))

# Keep the failing case IDs fixed so each completed plan item exposes its XPASSes.
XFAIL_GROUPS = (
    ("T6 preserves heading breaks where the schema can write them",
     _spec_ids(ALL_SPECS, "81 82 95") + ["breaks-in-headings", "breaks-in-tagged-headings"]),
    ("M1 aligns emphasis order and continuation with the reader",
     _spec_ids(EDITOR_SPECS, """
         393 394 395 399 404 406 410 411 413 414 415 416 418 419 422 424 428
         430 431 432 433 467 468 470 478 479 516 519 530 533
     """) + ["bold-inside-italic", "new-emphasis-marks-in-editor-order"]),
    ("M2 joins adjacent equal text runs as the reader does", ["adjacent-plain-and-marked-text"]),
    ("M3 normalizes emphasis boundaries that lose whitespace or punctuation",
     ["strike-trailing-space", "italic-space-after-bold-letter", "bold-quoted-letter-between-letters",
      "bold-colon-before-word", "emphasis-on-hard-break"]),
    ("M4 removes the duplicate mark inside the container",
     ["bold-repeated-inside-inline-container", "link-repeated-inside-inline-container"]),
    ("B1 fills parsed empty table cells to match editor cells",
     _spec_ids(EDITOR_SPECS, gfm="202 204") + ["filled-table-cell-keeps-source"],
     _CanonicalMismatch, _BaseSpellingMismatch),
    ("B1/B5 fill parsed empty list items and normalize the omitted tight attr",
     _spec_ids(EDITOR_SPECS, "280 281 282 283 284 315"),
     _CanonicalMismatch, _BaseSpellingMismatch),
    ("B2 normalizes a sole empty paragraph to an empty document",
     _spec_ids(ALL_SPECS, "484 487") + ["sole-empty-paragraph"]),
    ("B3 removes or writes a tag for a sibling empty paragraph",
     ["trailing-empty-paragraph", "trailing-empty-tagged-paragraph"]),
    ("B4 removes an empty list or table with no Markdown content", ["empty-bullet-list", "empty-table"]),
    ("B5 removes the blank line after a heading that changes list tightness",
     _spec_ids(ALL_SPECS, "300")),
    ("B5 removes the blank line after a thematic break that changes list tightness",
     ["tight-list-with-thematic-break"]),
    ("B5 normalizes a missing tight attr or one that differs from the reader's",
     _spec_ids(EDITOR_SPECS, """
         4 5 7 9 38 42 57 60 61 94 99 108 109 175 235
         254 255 256 257 258 259 260 262 263 264 265 267 268 270 271 273 274
         276 277 278 279 286 287 288 290 291 292 293 294 295 296 297 298 299
         301 302 303 305 306 307 308 309 310 311 312 313 314 316 317 318 319
         320 321 322 323 324 325 326
     """, "279 280") + ["missing-tight", "single-block-loose-list", "tight-list-needing-a-blank-line"]),
    ("B6 normalizes the header, alignment and paragraphs of a pipe table",
     ["table-without-header-row", "table-body-alignment", "table-cell-with-two-paragraphs"]),
    ("B7 pads a short table row as the reader does", ["ragged-table"]),
    ("W8 preserves loose lists that are read back as tight",
     _spec_ids(MARKDOWN_SPECS, "5 109 254 264 270 271 286 287 288 290") + ["loose-list-with-quote"]),
    ("E1 rejects touching emphasis that loses marks or becomes literal punctuation",
     ["touching-strike-inside-italic", "touching-crossed-bold-and-italic"], pytest.raises.Exception),
    ("E2 rejects a heading in a pipe table cell", ["heading-in-pipe-table-cell"], pytest.raises.Exception),
    # Masks use bold=1, italic=2 and strike=4 in run order.
    ("M1 orders combined or continued marks as the reader does",
     _run_ids("latin-spaced", "023 027 037 045 046 047 057 067 157 237 267 457 467") + _run_ids("latin-touching", """
         016 023 025 030 032 034 036 037 043 047 103 125 143 147 161 162 163 164
         165 167 203 216 230 232 234 236 237 243 247 251 252 254 256 257 263 267
         301 302 303 304 313 316 320 321 324 325 326 340 341 342 343 345 346 347
         362 363 364 365 373 374 376 403 416 423 425 430 432 434 436 437 452 461
         463 467 471 472 473 474 476 516 520 521 523 524 525 526 543 547 561 563
         571 572 610 612 613 614 615 616 623 625 630 631 632 634 636 637 643 647
         652 671 672 673 674 676 710 712 713 714 715 716 720 721 723 724 725 726
         730 732 734 736 737 740 741 742 743 745 746 747 752 757 761 762 763 764
         765
     """)),
    ("M1/M2 reorder combined marks and join runs as the reader does",
     _run_ids("latin-spaced", """
         003 007 033 077 223 227 233 277 333 337 377 445 446 447 455 466 477 557
         577 667 677 777
     """) + _run_ids("latin-touching", """
         003 033 116 166 223 225 233 255 300 322 330 332 333 334 336 337 344 366
         377 433 443 447 477 522 552 611 633 661 663 667 677 711 722 733 744 766
         771 772 773 774 776 777
     """)),
    ("M2 joins adjacent runs with the same marks as the reader does",
     _run_ids("latin-spaced", """
         000 001 002 004 005 006 011 022 044 055 066 111 113 115 117 133 155 177
         222 226 266 444 555 666
     """) + _run_ids("latin-touching", """
         000 001 002 004 011 022 044 100 110 111 112 113 114 115 122 133 144 155
         200 211 220 221 222 224 226 244 266 311 331 335 355 400 411 422 440 441
         442 444 445 446 455 466 511 533 544 551 553 554 555 556 557 566 577 622
         644 655 662 664 665 666 755 775
     """)),
    ("M3/M1/M2 normalize marks and runs where delimiters move marked spaces",
     _run_ids("latin-spaced", """
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
    ("E1 rejects touching emphasis that drops marks or produces literal delimiters",
     _run_ids("latin-touching", """
         005 006 007 017 027 050 051 052 053 054 055 056 057 060 061 062 063 064
         065 066 067 070 071 072 073 074 075 076 077 105 106 107 117 123 127 132
         136 150 152 160 170 171 172 173 174 175 176 177 205 206 207 213 217 227
         231 235 250 260 261 270 271 272 273 274 275 276 277 305 306 307 317 323
         327 350 352 357 360 361 367 370 371 372 405 406 407 417 427 450 460 470
         500 501 502 503 504 505 506 507 517 527 536 550 560 567 570 576 600 601
         602 603 604 605 606 607 617 627 635 650 657 660 670 675 700 701 702 703
         704 705 706 707 717 727 750 760 767 770
     """)),
    ("M1 addresses the shared bold and italic order reversed on reread",
     _run_ids("latin-touching", "253 532")),
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
    "x,dict_options,markdown_options,refuses,normalized",
    [_case(case_id, x, dict_options, markdown_options, refuses, normalized)
     for case_id, x, dict_options, markdown_options, refuses, normalized in EDITOR_DOCUMENTS],
)
def test_canonical_from_editor_document(x, dict_options, markdown_options, refuses, normalized):
    if refuses:
        with pytest.raises(tm.InvalidNodeError) as error:
            tm.from_dict(x, strict="content", **dict_options)
        assert error.value.code == "unrepresentable"
        return

    document = tm.from_dict(x, strict="content", **dict_options)
    _editor_invariants(x, document, dict_options)
    if "base" in dict_options:
        _base_spelling(document, dict_options["base"].to_markdown())
    _canonical_roundtrip(document, **markdown_options)
    if normalized is not None:
        assert document.to_dict() == normalized


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
