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

### Restricting link and image URIs

`[click](javascript:alert(1))` is valid Markdown, so marktip converts it by default.
A consumer that *stores* the result and renders it later can opt into a scheme allowlist, enforced in C++ rather than as a second traversal in Python:

```python
doc = tm.from_dict(ast, link_schemes=("http", "https", "mailto"), image_schemes=("https",))
```

`link_schemes` and `image_schemes` are separate because the asymmetry is the common case, and both default to `None`, which allows every scheme.
An empty tuple allows none.
Scheme comparison is case-insensitive, and entity references are resolved first, so neither `JavaScript:` nor `&#106;avascript:` slips past an `https`-only list.

`link_relative` and `image_relative` govern references that carry no scheme at all:

| | `/foo`, `#anchor`, `./x.png` | `//evil.com/x` |
| --- | --- | --- |
| `"allow"` (default) | passes | passes |
| `"path_only"` | passes | rejected |
| `"reject"` | rejected | rejected |

The two axes are independent: `link_relative="reject"` with no allowlist means "any scheme, but it must be absolute".

Both write boundaries take the same options, which matters when an editor submits an AST but agents and imports submit Markdown strings:

```python
doc = tm.from_markdown(untrusted, link_schemes=("https",), image_relative="reject")
# InvalidNodeError: link href scheme 'javascript' is not allowed
```

Violations raise `InvalidNodeError` with `.field` set to `"href"` or `"src"`.
The options are keyword-only.

### Refusing lossy conversions

Node and mark *types* are closed, but `attrs` are not.
An attr the serializer never reads is dropped without a word, so a `colspan: 2` cell quietly becomes a plain one:

```python
tm.from_dict(ast).to_markdown()                 # '| x |\n| --- |' — the colspan is gone
tm.from_dict(ast, strict=True)                  # InvalidNodeError: attr 'colspan' cannot be
                                                # expressed in markdown: GFM tables have no cell spanning
```

`strict=True` refuses anything markdown would drop or alter, from the walk that is already happening, so a consumer does not have to re-traverse the tree in Python to find out whether the document survives intact.
It is off by default and keyword-only, and it is a `from_dict` option only — the parser emits nothing but attrs it understands, with values in range, so there is nothing on the `from_markdown` path for it to catch.

| Node | Accepted attrs |
| --- | --- |
| `heading` | `level`: 1–6 |
| `codeBlock` | `language`, `info`: single-line `str` |
| `bulletList`, `taskList` | `tight`: `bool` |
| `orderedList` | `start`: 0–999999999, `tight`: `bool` |
| `taskItem` | `checked`: `bool` |
| `table` | `colCount`: non-negative `int` |
| `tableHeader`, `tableCell` | `align`: `"left"`/`"center"`/`"right"`/`None`, `colspan`: `1`, `rowspan`: `1`, `colwidth`: `None` |
| `image` | `src`, `alt`, `title`: `str` |
| `htmlBlock`, `htmlInline` | `html`: `str` |
| `link` mark | `href`, `title`: `str` |

Every other type takes no attrs at all.
Under strict, `bool` and `int` stay distinct — `{"level": True}` is refused rather than read as `1`.

`colspan`/`rowspan`/`colwidth` are *known* attrs whose only accepted values are the no-ops Tiptap's table extension puts on every cell.
Refusing the names outright would leave strict unusable for the documents it exists to check.
Tiptap's Link extension is the other direction: its default `target` and `rel` have no markdown form, so they are refused, which is the same rule that stops an `onclick` from vanishing silently.

Two attrs are accepted and then ignored, and they are the only two.
The serializer derives a table's column count from its rows, so `colCount` is never read, and it takes cell alignment from the header row only, so `align` on a body row is never read either.
Both are refused nowhere because `from_markdown` emits both: rejecting them would break re-parsing stored canonical Markdown on the read path, where a write-time refusal is much harder to notice.

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
For `from_markdown` it locates the node in the parsed document, since the input itself is a string.
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
| `disallowed_scheme` | `InvalidNodeError` | a link `href` / image `src` scheme is outside the allowlist |
| `disallowed_relative_url` | `InvalidNodeError` | a scheme-less `href`/`src` violates the relative policy |
| `invalid_uri_char` | `InvalidNodeError` | an `href`/`src` contains an ASCII control character |
| `unknown_attr` | `InvalidNodeError` | `strict`: the attr has no markdown form for that type |
| `invalid_attr_value` | `InvalidNodeError` | `strict`: the attr's value has the wrong type or is out of range |
| `unrepresentable` | `InvalidNodeError` | `strict`: the value is well-formed, but GFM cannot carry it |
| `markdown_max_depth` | `ParseError` | markdown nesting exceeds 2048 |
| `parse_failed` | `ParseError` | MD4C could not parse the input |

`from_markdown` still raises a plain `TypeError` when the argument is not `str`/`bytes` — that is a caller bug, not a malformed document.
So is a bad URI-policy option: a non-iterable `link_schemes` raises `TypeError`, and `link_schemes=("https://",)` or `link_relative="nope"` raises `ValueError`.

> **Changed in 0.4.0** — these were previously `ValueError` (`from_dict`) and `RuntimeError` (`from_markdown`).
> `MarktipError` derives from `Exception` directly, so `except ValueError` no longer catches them.

> **Changed in 0.5.0** — an ASCII control character in a link `href` or image `src` is now rejected outright, with or without the URI policy.
> A URI cannot carry one unencoded (`%09` is the encoded form), and leaving it in would defeat the allowlist itself, because browsers strip tab/LF/CR before reading the scheme.
> This also rejects `[x](<a\tb>)`, which CommonMark otherwise accepts.

> **Changed in 0.5.0** — an `orderedList` `start` outside 0–999999999 is clamped instead of emitted verbatim, and a code fence `language` is truncated at the first newline.
> Both previously produced output that reparsed into a different document; see [Defined normalizations](#defined-normalizations).

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
- **No ASCII control character** in a link `href` or image `src`, entity references included (`&Tab;`, `&#09;`).
- **The URI policy**, when `link_schemes`/`image_schemes`/`link_relative`/`image_relative` ask for it — see [Restricting link and image URIs](#restricting-link-and-image-uris).

A document that survives `from_dict` always serializes; callers do not need to re-check any of the above.
`from_markdown` enforces the same two URI rules on what it parses.

It deliberately does **not** validate, unless `strict=True` asks it to:

- **`attrs` names and value types.**
  Keys are free-form.
  `str`, `int`, and `bool` round-trip unchanged; anything else is coerced to a string (`[1, 2]` → `"[1, 2]"`, `1.5` → `"1.5"`, `None` → `""`), so `to_dict()` will not always give back what you passed in.
  An attr with no markdown form is dropped at serialization — see [Refusing lossy conversions](#refusing-lossy-conversions).
- **Per-node required attrs**, `strict` included.
  A `heading` without `level`, an `image` without `src`, or a `link` mark without `href` is accepted; the serializer substitutes a default rather than failing.
  `strict` governs the attrs that are present, not which ones must be.
- **Content models.**
  Which node may contain which is not checked — a `text` node directly under `doc` is accepted and serialized.
- **Raw HTML.**
  The URI policy governs `link` marks and `image` nodes, not markup inside `htmlBlock`/`htmlInline`, so `<a href="javascript:...">` passes it.
  Pair the policy with `html=False` to close that.
- **URI syntax beyond the scheme.**
  Everything after the scheme is opaque, and the stored value is never rewritten — an `href` is checked in its entity-decoded form but stored exactly as given.
  Under `link_relative="allow"` a protocol-relative `//evil.com/x` also passes, since it carries no scheme; `"path_only"` is the setting that rejects it.

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
- **Ordered list start** — clamped to CommonMark's 0–999999999 (`-5` → `0.`), and the running number stops at that ceiling rather than emitting a 10-digit marker. Only the first number is honoured on reparse, so a repeated ceiling changes nothing.
- **Code fence info strings** — a `language` is truncated at the first newline, since an info string is a single line; one containing a backtick switches the fence to `~~~`, which carries it losslessly.
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
