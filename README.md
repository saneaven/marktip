# marktip

Fast C++/MD4C Markdown conversion for Tiptap-style JSON.

## Installation

```bash
python -m pip install marktip
```

Release wheels are built for common CPython versions on Linux, macOS, and Windows.
If a wheel is not available for a platform, pip can build from the source distribution with a C++17 compiler and standard Python build tooling.

## Usage

```python
import marktip as tm

doc = tm.from_markdown("# Hello")
ast = doc.to_dict()
markdown = doc.to_markdown()

doc = tm.from_dict(ast)
```

`from_markdown` follows GFM/CommonMark by default.
Pass `cjk_friendly=True` to relax the emphasis and strikethrough rules so delimiters next to CJK text still open and close (e.g. `**볼드**은` parses as bold), a non-standard extension that is off by default:

```python
doc = tm.from_markdown("**볼드**은 강조", cjk_friendly=True)
```

Strikethrough follows the GFM reference implementations (cmark-gfm/micromark): intra-word `~~` strikes (`a~~b~~c`), including next to CJK letters (`~~삭제~~은`).
`cjk_friendly` still matters for `*`/`_`, and for `~` in punctuation-adjacent cases such as `~~"인용"~~라고`.

Pass `html=False` to parse raw HTML as literal text instead of `htmlBlock`/`htmlInline` nodes.
Content is preserved (the serializer escapes it), and `<br>` inside table cells still maps to `hardBreak` so marktip's own table output round-trips:

```python
doc = tm.from_markdown("a <u>x</u> b", html=False)
# paragraph with the literal text "a <u>x</u> b"
```

marktip targets GFM core syntax and canonical Markdown output rather than byte-identical source preservation.

## Errors

Every rejection marktip raises derives from `marktip.MarktipError`, so "the input is malformed" is a single `except` — no need to catch a bare `ValueError` wide enough to swallow an unrelated bug:

```python
try:
    tm.from_dict(payload).to_markdown()
except tm.MarktipError as e:
    return 422, {"code": e.code, "path": e.path, "detail": e.detail}
```

```
Exception
└─ MarktipError              .code, .path, .detail
   ├─ UnknownTypeError       + .type, .kind    — type outside the closed schema
   ├─ InvalidNodeError       + .field          — violates the node grammar
   └─ ParseError                               — markdown could not be parsed
```

`.path` is a breadcrumb into the input, e.g. `content[1].content[0].marks[0]`; it is `""` when the failure is at the root or has no location.
`.detail` is the same string as `str(e)`.
`.code` is a stable machine key:

| `.code` | Class | Raised when |
| --- | --- | --- |
| `unknown_node_type` | `UnknownTypeError` | node `type` is outside the closed schema |
| `unknown_mark_type` | `UnknownTypeError` | mark `type` is outside the closed schema |
| `missing_type` | `InvalidNodeError` | a node or mark has no `type` key |
| `invalid_root` | `InvalidNodeError` | the root node's type is not `doc` |
| `wrong_type` | `InvalidNodeError` | `attrs`/`content`/`marks`/a child has the wrong Python type |
| `max_depth` | `InvalidNodeError` | dict nesting exceeds 2048 |
| `markdown_max_depth` | `ParseError` | markdown nesting exceeds 2048 |
| `parse_failed` | `ParseError` | MD4C could not parse the input |

`from_markdown` still raises a plain `TypeError` when the argument is not `str`/`bytes` — that is a caller bug, not a malformed document.

> **Changed in 0.4.0** — these were previously `ValueError` (`from_dict`) and `RuntimeError` (`from_markdown`).
> `MarktipError` derives from `Exception` directly, so `except ValueError` no longer catches them.

## What `from_dict` validates

The Tiptap-side schema is closed: every node/mark type must have a markdown mapping.
`from_dict` is the single enforcement point and rejects unknown types instead of silently dropping content.
It guarantees, for the whole tree:

- **Closed schema.**
  Node types are `doc`, `paragraph`, `text`, `hardBreak`, `heading`, `blockquote`, `codeBlock`, `horizontalRule`, `bulletList`, `orderedList`, `listItem`, `taskList`, `taskItem`, `table`, `tableRow`, `tableHeader`, `tableCell`, `image`, `htmlBlock`, `htmlInline`.
  Marks are `bold`, `italic`, `strike`, `code`, `link`.
  Anything else → `UnknownTypeError`.
- **`type` is required** on every node and mark.
- **The root is a `doc`.**
- **Shapes**: `attrs` is a dict, `content` and `marks` are lists, and every entry of `content`/`marks` is a dict.
- **Depth** is at most 2048 levels.

A document that survives `from_dict` always serializes; callers do not need to re-check any of the above.

It deliberately does **not** validate:

- **`attrs` value types.**
  Keys are free-form.
  `str`, `int`, and `bool` round-trip unchanged; anything else is coerced to a string (`[1, 2]` → `"[1, 2]"`, `1.5` → `"1.5"`, `None` → `""`), so `to_dict()` will not always give back what you passed in.
- **Per-node required attrs.**
  A `heading` without `level`, an `image` without `src`, or a `link` mark without `href` is accepted; the serializer substitutes a default rather than failing.
- **Content models.**
  Which node may contain which is not checked — a `text` node directly under `doc` is accepted and serialized.

Structural violations report where they happened:

```python
try:
    tm.from_dict({"type": "doc", "content": [{"content": []}]})
except tm.InvalidNodeError as e:
    e.code    # "missing_type"
    e.field   # "type"
    e.path    # "content[0]"
    e.detail  # "node is missing required key 'type'"
```

## Defined normalizations

Markdown cannot represent every Tiptap document exactly.
Rather than emitting markdown that reparses into a different structure, marktip applies these deterministic (and idempotent) normalizations at serialization time:

- **Hard breaks in headings** — ATX headings are single-line, so a `hardBreak` (or a literal newline carried over from setext input) inside a heading serializes as a single space: `heading("a", hardBreak, "b")` → `# a b`.
- **Multi-block table cells** — blocks inside a cell are joined with `<br>` and the cell is flattened to one line; two paragraphs in a cell reparse as one paragraph containing a `hardBreak`.
- **Headerless tables** — GFM tables require a header row, so the first row is always emitted as the header; a leading `tableCell` row reparses as `tableHeader`.
- **Heading levels** — clamped to 1–6 at serialization (`0` → `#`, `7` → `######`).
- **Emphasis boundary whitespace** — whitespace touching an emphasis delimiter has no valid markdown form and is expelled outside the marks (`bold("굵게 ")` → `**굵게** `), cf. prosemirror-markdown's `expelEnclosingWhitespace`.
- **Adjacent same-family lists** — consecutive lists of the same family alternate markers (`-`/`*`, `1.`/`1)`) so they stay separate lists on reparse instead of merging (which would renumber ordered items or spread task checkboxes).

## Development

```bash
python -m pip install .[test]
python -m pytest
```

For a direct local CMake build:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
cmake --build build
PYTHONPATH=python python -m pytest
PYTHONPATH=python python scripts/benchmark.py
```
