# marktip

Fast C++/MD4C Markdown conversion for Tiptap-style JSON.

## Installation

```bash
python -m pip install marktip
```

Release wheels are built for common CPython versions on Linux, macOS, and
Windows. If a wheel is not available for a platform, pip can build from the
source distribution with a C++17 compiler and standard Python build tooling.

## Usage

```python
import marktip as tm

doc = tm.from_markdown("# Hello")
ast = doc.to_dict()
markdown = doc.to_markdown()

doc = tm.from_dict(ast)
```

`from_markdown` follows GFM/CommonMark by default. Pass `cjk_friendly=True` to
relax the emphasis and strikethrough rules so delimiters next to CJK text still
open and close (e.g. `**볼드**은` parses as bold), a non-standard extension that
is off by default:

```python
doc = tm.from_markdown("**볼드**은 강조", cjk_friendly=True)
```

Strikethrough follows the GFM reference implementations (cmark-gfm/micromark):
intra-word `~~` strikes (`a~~b~~c`), including next to CJK letters
(`~~삭제~~은`). `cjk_friendly` still matters for `*`/`_`, and for `~` in
punctuation-adjacent cases such as `~~"인용"~~라고`.

Pass `html=False` to parse raw HTML as literal text instead of
`htmlBlock`/`htmlInline` nodes. Content is preserved (the serializer escapes
it), and `<br>` inside table cells still maps to `hardBreak` so marktip's own
table output round-trips:

```python
doc = tm.from_markdown("a <u>x</u> b", html=False)
# paragraph with the literal text "a <u>x</u> b"
```

marktip targets GFM core syntax and canonical Markdown output rather than
byte-identical source preservation.

## Schema enforcement

The Tiptap-side schema is closed: every node/mark type must have a markdown
mapping. `from_dict` rejects unknown types instead of silently dropping
content, raising `marktip.UnknownTypeError` — a `ValueError` subclass with
structured fields for programmatic relay:

```python
try:
    tm.from_dict({"type": "doc", "content": [{"type": "callout"}]})
except tm.UnknownTypeError as e:
    e.type    # "callout"
    e.kind    # "node" or "mark"
    e.path    # "content[0]"
    e.detail  # "unknown node type 'callout' at content[0]"
```

Known node types: `doc`, `paragraph`, `text`, `hardBreak`, `heading`,
`blockquote`, `codeBlock`, `horizontalRule`, `bulletList`, `orderedList`,
`listItem`, `taskList`, `taskItem`, `table`, `tableRow`, `tableHeader`,
`tableCell`, `image`, `htmlBlock`, `htmlInline`. Known marks: `bold`,
`italic`, `strike`, `code`, `link`.

## Defined normalizations

Markdown cannot represent every Tiptap document exactly. Rather than emitting
markdown that reparses into a different structure, marktip applies these
deterministic (and idempotent) normalizations at serialization time:

- **Hard breaks in headings** — ATX headings are single-line, so a `hardBreak`
  (or a literal newline carried over from setext input) inside a heading
  serializes as a single space: `heading("a", hardBreak, "b")` → `# a b`.
- **Multi-block table cells** — blocks inside a cell are joined with `<br>`
  and the cell is flattened to one line; two paragraphs in a cell reparse as
  one paragraph containing a `hardBreak`.
- **Headerless tables** — GFM tables require a header row, so the first row is
  always emitted as the header; a leading `tableCell` row reparses as
  `tableHeader`.
- **Heading levels** — clamped to 1–6 at serialization (`0` → `#`, `7` →
  `######`).
- **Emphasis boundary whitespace** — whitespace touching an emphasis delimiter
  has no valid markdown form and is expelled outside the marks
  (`bold("굵게 ")` → `**굵게** `), cf. prosemirror-markdown's
  `expelEnclosingWhitespace`.
- **Adjacent same-family lists** — consecutive lists of the same family
  alternate markers (`-`/`*`, `1.`/`1)`) so they stay separate lists on
  reparse instead of merging (which would renumber ordered items or spread
  task checkboxes).

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
