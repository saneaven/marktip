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

### What changed in 0.9.0

- Python documents support `==` and `hash()`, and JavaScript documents support `equals()`.
  If a save puts a stored document back into a live editor, compare documents with `equals()` in JavaScript or `==` in Python.
  Comparing JSON strings can make a save replace the editor contents each time the user types a trailing space.
- The stored tree can differ from the JSON submitted to `from_dict`.
  Normalization leaves the live editor's tree alone.
  `from_markdown(...).to_dict()` also changes.
  Code block text loses the final fence newline, and empty cells, list items, task items and blockquotes gain an empty paragraph.
  Paragraphs and headings lose line-edge whitespace even in tag form or inside a link or declared mark, with code spans preserving their spaces.
  Paragraphs keep leading hard breaks and lose trailing ones, including in table cells.
  In the default schema, the dict heading `heading[a, hardBreak, b]` and the Markdown heading `a\nb\n===\n` both store the single line `a b`.
  With `core_attrs={"heading": {}}`, both keep their breaks.
  Their outputs, shown with backslashes and newlines escaped, are `<h2>a\\\nb</h2>` and `<h1>a\nb</h1>`.
  Some mark orders change on Markdown input, and edge whitespace supplied by a character reference can be trimmed or lose its emphasis too.
  With `UNDERLINE` declared, reading `**a <u>b</u>**` now leaves the space before `<u>` plain.
- Canonical hard breaks now use a backslash and a newline, with `<br>` in pipe cells.
  Fences write the full info string and always put a newline after the body, so an empty fence has an empty line.
  Fence word recognition follows md4c, so tab-led info no longer selects a declared fence carrier.
  Loose lists write blank lines inside items, and overlapping marks from an editor can be written in a different order.
  A checkbox-only line no longer produces an empty leading paragraph before an item's first block.
- Plain text from dict input such as `visit https://example.com or www.example.com or a@b.com today` now writes as `visit https\://example.com or www\.example.com or a\@b.com today` and reads back as plain text.
  Code spans containing only spaces write without padding.
  A paragraph's second line gets a backslash before a leading `|` or `:`.
  Link destination backticks are escaped, and an empty destination with a title writes as `<>`.
- In a schema with paragraph tags, kept empty paragraphs write as `<p></p>`, including trailing editor paragraphs and sole paragraphs in otherwise empty declared containers.
  The sole filler paragraph in a list item, task item, table cell or blockquote stays unwritten.
  With heading tags, `| ## title |` becomes `| <h2>title</h2> |` for a cell containing a heading, including when the schema also has table tags.
  Tag-form lists and tables write the normalized attrs `tight`, `start` on ordered lists, and `colCount` on tables.
- Markdown and dict conversion can now raise `invalid_content` if removing an empty block leaves a required child that normalization cannot create.
  For example, with table tags enabled, a declared `callout` with `content="table+"` fails if its only child is an empty `<table>`.
  Both conversions accepted that input in 0.8.3.
  The error can also occur on dict input with `strict="off"`.
- Strict editor saves can raise `InvalidNodeError` with code `unrepresentable` for emphasis the canonical writer cannot carry or for a pipe cell it cannot carry.
  Display the error to the editor user.
  Pass `cjk_friendly=True` to `from_dict` or `cjkFriendly: true` to `fromDict` when that Markdown will be read in CJK-friendly mode.
- The remembered bytes can differ from the normalized tree.
  For example, `~~b&#32;~~` loses its trailing space, and an empty link such as `[](./target.md)` has no node.
  Both spellings survive in remembered Markdown.
  Policy checks now run before normalization and `base=` inheritance, so an inherited value is outside the current call's policy check.
- The dump format stays the same.
  `load()` restores 0.8 dumps as stored, including their mark order.
  Legacy states such as edge whitespace inside emphasis, a final newline in code text or edge hard breaks can write Markdown that reads back differently.
  Save once through `from_dict(load(x).to_dict())` to normalize the document, passing the schema and reading options in use.
  A 0.8 dump of a fence containing the single line `x` still stores `x\n` after this resave.
  A canonical write adds its own newline, so the rewritten fence has a visible empty line after `x`.

See [Defined normalizations](#defined-normalizations) for the input, writing and strict-check rules.

> **Changed in 0.8.0** — `to_markdown()` returns the Markdown a document was read from, and marktip's own spelling only for blocks that changed;
> pass `canonical=True` for the previous output.
> Nesting is limited to 512 levels instead of 2,048.
> A table whose header and delimiter rows disagree on the cell count is read as a paragraph, as GFM specifies, instead of losing the extra header cells.
> `Schema(block_image=...)` takes a real `bool`.
> New in this release: `dump()` and `load()`, `from_dict(base=)`, `from_markdown(partial=, keep_source=)`, and a WebAssembly build with a JavaScript package.

`from_markdown` follows GFM/CommonMark by default.
Pass `cjk_friendly=True` to follow the [CommonMark CJK-friendly Amendments Specification](https://github.com/tats-u/markdown-cjk-friendly/blob/main/specification.md) for emphasis (`*`, `_`) and strikethrough (`~`). This opt-in extension recognizes CJK punctuation as well as letters, so `**《제목》**a`, `a**《제목》**`, and `**「約束」**a` retain their bold marks:

```python
doc = tm.from_markdown("**볼드**은 강조", cjk_friendly=True)
```

`from_dict(..., cjk_friendly=True)` uses the same rules to normalize and check emphasis for Markdown that will be read in that mode.

Strikethrough follows the GFM reference implementations (cmark-gfm/micromark): intra-word `~~` strikes (`a~~b~~c`), including next to CJK letters (`~~삭제~~은`).
`cjk_friendly` still matters for punctuation-adjacent cases such as `~~"인용"~~라고`.

The CJK classifier uses Unicode 17.0.0 East Asian Width `W`, `F`, or `H` (excluding default emoji presentation characters), plus the Hangul script. This includes fullwidth digits such as `１`. Before a delimiter, CJK characters followed by a non-emoji general-use variation selector (`U+FE00`–`U+FE0E`) are classified as one sequence; ideographic variation selectors (`U+E0100`–`U+E01EF`) and standardized fullwidth quotation-mark sequences are also recognized. `U+FE0F` is an emoji presentation selector and is excluded from that sequence rule.

Underscores retain CommonMark's additional restriction on emphasis inside words. The CJK-friendly specification changes delimiter flanking without removing that protection for names such as `snake_case`: `_《제목》_을` and `__《제목》__을` stay literal, even with `cjk_friendly=True`. Use `*` or `**` when emphasis must adjoin a word.

> **Changed in 0.7.3** — CJK-friendly character classification, variation-selector sequences, flanking, and underscore conditions follow the specification. The same flanking rules apply to `~~`. An editor document containing bold `《제목》` followed by `a` now survives serialization and reparsing with `cjk_friendly=True`.

Pass `html=False` to parse undeclared HTML as literal text instead of `htmlBlock`/`htmlInline` nodes.
Declared tags are recognized with either setting when exposed as tag constructs.
With `html=True`, an undeclared HTML block or comment remains raw as a whole, including declared-looking tags inside it.
Content is preserved in the node tree, and the canonical writer escapes it.
`<br>` inside table cells still maps to `hardBreak` so marktip's own table output round-trips:

```python
doc = tm.from_markdown("a <u>x</u> b", html=False)
# paragraph with the literal text "a <u>x</u> b"
```

Pass `partial=True` to read an open declared tag as closed where its parent ends.
The resulting tree is the same as if its closing tag were there, including the usual completion of missing content.
Closing tags without an opening tag, attr errors inside complete tags, and content-model violations still raise errors;
a container's closing tag is still an error while a container opened inside it is still open.
Marks crossing an inline container's boundary also remain errors with `partial=True`.
`partial` is keyword-only and defaults to `False`.
Incomplete tags such as `<callout tone="no`, `</call`, and `<mention id="1"` are read as text even with `partial=True`, like `**bo`.
Where that text does not fit its parent's content model, the input raises `invalid_content` until the tag is complete; this affects tag-form tables and lists and containers with narrow content models.

Parsed documents remember source spelling at the top level by default.
`to_markdown()` returns the remembered text of unchanged blocks, while `to_markdown(canonical=True)` writes the whole document in marktip's spelling.
Pass `keep_source=False` to skip remembering source spelling without changing the node tree.
Then `to_markdown()` equals `to_markdown(canonical=True)`, and `dump()` has no `source` field.
`keep_source` is keyword-only and defaults to `True`; it is independent of `partial`.

### Markdown round trips

1. Unchanged blocks return their remembered Markdown byte for byte, subject to the [source-spelling limits](#source-spelling-limits).
2. Reading `d.to_markdown(canonical=True)` gives the same document as `d`, apart from attrs the Markdown omits.
3. Writing the re-read document canonically gives the same bytes.

Use the same schema and reading options for the round trip, and use `strict="content"` or `strict="exact"` on dict input.
An editor's submitted tree can change as described in [Defined normalizations](#defined-normalizations).

Rules 2 and 3 do not cover emphasis in `from_markdown` output or in blocks that inherit remembered text, which skip the strict read-back check.
For example, `from_markdown("**a**[**b**](u)c")` writes canonically as `**a[b](u)**c`.
Reading that back changes the tree, and the next canonical write gives `\*\*a[b](u)\*\*c`.
The original tree still passes strict `from_dict` when it inherits the original Markdown through `base=`.

### Comparing documents

Use `a == b` in Python and `a.equals(b)` in JavaScript.
Equality compares the schema fingerprint and the tree, including node types, text, attrs, stored mark order and child order.
Attr key order is ignored for nodes and marks.
Attrs omitted from Markdown still count.
Remembered spelling is ignored.
Equal Python documents have the same `hash()`.
Python's `__eq__` returns `NotImplemented` for another type, and JavaScript's `equals()` returns `false` for anything other than a `Document`.

Compare `to_markdown()` or `toMarkdown()` for the actual source-preserving output.
Use the canonical option on those methods to compare only what marktip's Markdown writer emits.

### Remembering source spelling

A `Document` holds the Tiptap node tree and, when available, the Markdown spelling of its top-level blocks.
The remembered text includes list markers, emphasis delimiters, tag attr order, reference links, whitespace, and line endings:

```python
source = "\nTitle\n=====\n\n* first\n* second\n"
doc = tm.from_markdown(source)
assert doc.to_markdown() == source
assert doc.to_markdown(canonical=True) == "# Title\n\n- first\n- second"

stored = doc.dump()
base = tm.load(stored)
edited = tm.from_dict(base.to_dict(), base=base)
assert edited.to_markdown() == source
```

`from_markdown` creates the spelling unless `keep_source=False`.
`from_dict(editor_json, base=stored_document)` borrows it for matching blocks, and `load` restores it from stored data.
`from_dict` without a base writes canonical Markdown.
A base without spelling lends no text or gaps.
With a matching schema declaration, it still fills absent attrs on matched blocks.
The base only lends spelling and absent attrs; it does not merge changes from two writers.

Blocks match after normalization when type, text, children, and Markdown-carried attrs agree throughout their subtrees.
Marks are compared without regard to order.
Attrs carried by a declared tag count too; presentation and free-form attrs that Markdown does not carry do not count.
Among equal base blocks, matching first prefers an unused block that keeps the base order, then an unused moved block.

An attr key absent from the editor's JSON means the editor does not model it.
On a matched block, the value comes from the node or mark at the corresponding position in the base.
This preserves attrs such as `tight`, `info`, and an old editor's cell `align` when the block matches.
After inheritance, mark order, fence info, list tightness, table width and pipe-table alignment are adjusted again.
A key present with `null` was cleared and is not inherited.
An unmatched block inherits no attrs.
Strict input validation runs before inheritance, so an absent required attr is an error even if a base could supply it.
The strict check for a paragraph join that would lose a tag attr also runs while reading the dict.
The remaining pipe-cell checks and the emphasis check run on the final tree and skip blocks that inherited remembered text.

Top-level reference-definition paragraphs are remembered as source-only pieces.
They follow their preceding matched base block when it moves; if that base block is not matched, they follow the nearest earlier surviving match or stay at the front.

The writer applies three rules:

1. A piece with remembered text writes that text; a block without it uses marktip's writer.
2. Pieces use their remembered trailing gaps.
   A gap without a blank line is kept only between two pieces that both retain text and were neighbours in the source; otherwise the writer inserts one blank line.
   A final gap is kept only when the last emitted piece retains its text.
   A block that writes nothing drops together with its gap.
3. Adjacent Markdown lists use different markers, including lists that keep their text.
   Newly written lists take account of both neighbours' actual markers.
   When two original lists become neighbours with the same marker, the later one is written anew.
   If a new ordered list cannot use a marker different from both original neighbours, the colliding right-hand list is written anew instead.

### Storing and restoring a document

Store one `dump()` result per document.
It is JSON-serializable, and its `doc` field equals `to_dict()`:

```python
import json

stored = json.loads(json.dumps(doc.dump()))
restored = tm.load(stored)
assert restored.to_dict() == doc.to_dict()
assert restored.to_markdown() == doc.to_markdown()
```

The stored form has this shape, with `doc.content` abbreviated:

```json
{
  "marktip": 1,
  "schema": "d4657f55662f817f",
  "doc": {"type": "doc", "content": [...]},
  "source": {
    "head": "",
    "items": [
      {"text": "Title\n=====", "sep": "\n\n"},
      {"sep": "\n\n"},
      {"text": "* first\n* second", "sep": "\n\n"},
      {"text": "[ref]: https://example.com", "sep": "\n", "node": false}
    ]
  }
}
```

Items without `"node": false` correspond in order to the children of `doc.content`.
An item without `text` has no remembered spelling; `sep` is its trailing gap.
`head` holds text before the first piece.
`dump` stores the gaps the writer would actually use, so loading an inherited or edited document does not invent original adjacency.
A document without spelling omits `source` entirely and still round-trips through `dump` and `load`.

The schema is compared by a stable fingerprint of its declaration, so separately constructed equal schemas can reuse spelling through both `base=` and `load`.
The core computes the fingerprint with FNV-1a 64-bit and stores it as 16 hexadecimal characters.
`load(data, schema=S)` reads the stored content and restores spelling only when the declaration fingerprint matches.
The content must be readable under the supplied schema.
A different declaration drops the spelling, so readable content is written in marktip's spelling.

`load` trusts that the stored spelling denotes the stored content; it does not reparse the text to check it.
An unknown `marktip` version raises `ValueError`.
If the source's block-piece count does not match the root's child count, the spelling is dropped.

For the default schema, the caller's flow is:

| Action | Code | Conversion |
| --- | --- | --- |
| Agent writes | `from_markdown(md).dump()` | Parse once |
| Frontend renders or opens the editor | Read the stored `doc` | None |
| Editor saves | `from_dict(editor_json, base=load(stored), strict="content").dump()` | Read JSON twice, compare blocks and check any emphasis that needs writing |
| Agent reads | `load(stored).to_markdown()` | Read JSON once and join pieces |

Pass the application's schema when restoring a configured document.
The frontend can render the stored `doc` without running marktip.

### Source-spelling limits

- Dumps stored before the FNV-1a fingerprint change are read without their source spelling; their content stays intact.
- Changing parser options (`html`, `cjk_friendly`) can make documents stored earlier read back differently.
- The unit is one top-level block.
  When a list, table, quote, or declared container needs rewriting, that whole block is written again and its internal source spelling is lost.
- When identical blocks occur together and one is deleted, which original spelling the survivor inherits is unspecified.
- Adding a block after an original unclosed code fence or an HTML block such as an unclosed `<script>` can put the added block inside it on readback.
- The remembered text of a document read with `partial=True` can contain open declared tags.
  That text needs `partial=True` to be read again.
  The canonical writer closes declared containers that remain in the tree after normalization.
  On readback with `partial=True`, a block added after an open top-level container is read as inside it.
- An original block beginning with spaces can be absorbed into a list if it is moved directly after that list or if the block between them is deleted; two original indented code blocks that become neighbours after deletion or movement can read back as one code block.
- Reference definitions inside a quote, list, or the start of a paragraph disappear when that containing block is rewritten.
  Other unchanged blocks using those definitions can then re-read their reference links as literal text.
- The remembered text of a block dropped as empty stays in the output.
  Adding or rewriting surrounding blocks can change how that text reads back.
- If an editor omits a cell's `align` but keeps `tight`, a tag-form table in a tight list item can lose its match and remembered spelling.
- In a schema without table tags, resubmitting a table with only a header cell's `align` key omitted can lose the column's alignment and the table's remembered spelling even with `base=`.
- Adjacent links to the same destination can merge before matching if the caller omits the attr that distinguished them, such as the second link's `title`.
  The merged block loses the attr and the remembered spelling.
  Conversely, submitting two equal link runs with `target` omitted from only one can keep them separate, so they no longer match a base that joined them.
- An inline container's link and an inner link can become equal when the caller omits an attr on the outer link.
  Normalization then removes the inner link, and the block can lose the inherited attr and its spelling.
- Emphasis cleanup uses the link's form before inheritance.
  If the caller omits `target` from a tag-form link, normalizing it as a Markdown link can move emphasis boundaries and prevent the block from inheriting the attr and its spelling.
- Resubmitting an unchanged 0.8 dump through `base=` can lose spelling if the older tree has adjacent equal-mark runs that now join.
- Two remembered lists that become neighbours can share a marker.
  The writer can then regenerate one of those lists even though its remembered spelling exempted it from the strict emphasis check.
- Adjacent links distinguished only by a Markdown-omitted attr can fail the strict emphasis check if the reader merges them.
- With `block_image=True`, a top-level paragraph replaced by exactly one node keeps its text.
  A paragraph that really splits into several nodes loses its text; unchanged blocks around it keep theirs.
- A source-preserving dump stores both node content and remembered Markdown, so remembered text increases the stored size.
  The stored `doc` is marktip's normalized conversion result, not an untouched copy of the editor's submitted JSON.
- Rewritten blocks use `\n`, so an original CRLF document can acquire mixed line endings.
  Markdown NUL characters are replaced with U+FFFD before their spelling is remembered.
- Concurrent agent and editor writes are outside this feature.
  The caller must use revision checks to reject an editor save based on an outdated document.

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

Violations raise `InvalidNodeError` with `.field` set to the URI attr name (`"href"` or `"src"` for core links and images).
Declared `Attr(str, uri="link")` and `uri="image"` attrs use the corresponding policy too.
For a declared URI attr or an active core link/image tag form,
both the stored value and its entity-decoded form must pass because a tag carries the stored string.
The options are keyword-only.

### Rejecting node types

marktip's schema includes every node it can serialize, but an application may use a smaller ProseMirror dialect.
Both write boundaries accept `reject_node_types`, so that dialect can be enforced after either Markdown parsing or dict conversion without a second application-side tree walk:

```python
NO_RAW_HTML = ("htmlBlock", "htmlInline")

doc = tm.from_dict(editor_json, reject_node_types=NO_RAW_HTML)
doc = tm.from_markdown(imported_markdown, reject_node_types=NO_RAW_HTML)
```

`None` (the default) rejects nothing; an empty iterable has the same effect.
Every entry must name a node type in the schema passed to the call, and matching is exact and case-sensitive.
Declared node names are accepted too.
A bare string or a non-string entry raises `TypeError`; an unknown node name raises `ValueError`.
A configured type in the input tree raises `InvalidNodeError` with `.code == "disallowed_node_type"`, `.field == "type"`, and `.path` locating the node.
Normalization can add required fillers after the check, so those fillers are outside the policy.
The option is keyword-only.

This differs from `html=False`: `html=False` preserves raw markup as escaped literal text on Markdown input, while rejecting `htmlBlock`/`htmlInline` refuses markup that parsed as a raw-HTML node.
`reject_node_types` also works for dict input, where there is no parser flag.

### Refusing lossy conversions

Node and mark *types* are always closed by the selected schema, but fields, attrs and content models are only closed on dict input when `strict` is enabled.
The examples and core attr table below use the default schema.
[Extending the schema](#extending-the-schema) adds carried attrs and types without changing that default.
An attr the serializer never reads is left out of the Markdown without a word, so a `colspan: 2` cell quietly becomes a plain one:

```python
tm.from_dict(ast).to_markdown()                 # '| x |\n| --- |' — the colspan is gone
tm.from_dict(ast, strict="content")             # InvalidNodeError: attr 'colspan' cannot be
                                                # expressed in markdown: GFM tables have no cell spanning
```

`strict` names what the conversion must carry.
It is keyword-only and a `from_dict` option only.
`from_markdown` validates declared tags, attrs and content as it reads them; that validation is always enabled.
The strict dict checks for emphasis and pipe cells are described under [Defined normalizations](#what-strict-refuses).

| `strict` | Checks |
| --- | --- |
| `"off"` (default) | no strict checks or round-trip guarantees |
| `"content"` | content and structure, including closed node fields and content models. Known presentation attrs are type-checked and stored, then omitted from Markdown |
| `"exact"` | the content checks, plus refusal of supplied attrs with no Markdown form. Declared defaults mean unset |

Normalization still adjusts attrs at every level, including `"exact"`.
For example, with `language: "python"` and `info: "ruby numbered"`, the stored `info` becomes `"python"`.
In a schema without table tags, a body cell's `align: "right"` becomes `"left"` when its header is left aligned.
A single-item, single-block list with `tight: false` becomes `tight: true`.

Both enabled levels also enforce the schema's mark exclusions and refuse duplicate marks with equal type and attrs.
The standard marks represented by marktip are self-exclusive, so a node cannot carry the same mark type twice — including two `link` marks with different destinations.
The conflicting mark is rejected with `InvalidNodeError` rather than being serialized into Markdown that reparses with different formatting or structure.
`strict="off"` skips this check because strict validation is disabled.

Both enabled levels reject a node or mark top-level key that its type does not declare (`unknown_field`), and enforce the following content models (`invalid_content`):

| Parent | Allowed children |
| --- | --- |
| `doc`, `blockquote`, `listItem`, `taskItem`, `tableCell`, `tableHeader` | block nodes |
| `paragraph`, `heading` | inline nodes (`text`, `hardBreak`, `image`, `htmlInline`) |
| `codeBlock` | unmarked `text` only |
| `bulletList` | `listItem` |
| `orderedList` | `listItem`, `taskItem` |
| `taskList` | `taskItem` |
| `table` | `tableRow` |
| `tableRow` | `tableHeader`, `tableCell` |
| `text`, `hardBreak`, `horizontalRule`, `image`, `htmlBlock`, `htmlInline` | none |

Block nodes are `paragraph`, `heading`, `blockquote`, `codeBlock`, `horizontalRule`, `bulletList`, `orderedList`, `taskList`, `table`, and `htmlBlock`.
A strict text node must carry a non-empty string `text` field.
This is marktip's canonical child grammar, not a verbatim copy of one editor's schema: in particular, ordered Markdown task items remain `orderedList` → `taskItem`, and empty parser-produced containers remain valid.
These rules prevent a nested block submitted inside a paragraph, content attached to a leaf, or an arbitrary child key from being silently flattened or omitted by the serializer.

> **Changed in 0.7.2** — `strict="content"` and `strict="exact"` now close node/mark top-level fields and per-node content models with `unknown_field` and `invalid_content`. `strict="off"` keeps the previous permissive converter behavior.

> **Changed in 0.7.1** — `strict="content"` and `strict="exact"` now reject duplicate same-type marks with `invalid_mark_set`. Markdown parsing collapses nested spans that map to the same self-exclusive mark, so parser output remains valid on the strict read path.

The two levels differ over one thing, and it is worth being precise about which:

```python
# what a stock Tiptap Link extension submits for a link with only href set
mark = {"type": "link", "attrs": {"href": "https://a", "target": "_blank",
                                  "rel": "noopener noreferrer nofollow",
                                  "class": None, "title": None}}

tm.from_dict(ast, strict="content")             # fine — target and rel are not written
tm.from_dict(ast, strict="exact")               # InvalidNodeError: attr 'target' cannot be expressed
                                                # in markdown: a markdown link carries only a
                                                # destination and a title
```

Dropped here means left out of the Markdown.
The document keeps the attr, so `to_dict()` and `dump()` still carry it, and only `to_markdown()` omits it.

Dropping that `target` costs the *author* nothing — the editor stamped it on and nobody wrote it.
Dropping a `colspan` moves every cell after it under a different header, so `"content"` refuses that one too.
Nothing in the JSON tells the two apart: ProseMirror serializes schema defaults onto every node, so a chosen `target` and a stamped one arrive identical.
Choose `"content"` to accept those presentation attrs in stored documents and omit them from Markdown.
Choose `"exact"` to require a Markdown form for them.
Both modes apply the same [attr normalizations](#what-the-inputs-normalize).

| Node | Accepted attrs | Dropped, no markdown form |
| --- | --- | --- |
| `heading` | `level`: 1–6 | |
| `codeBlock` | `language`, `info`: single-line `str` | |
| `bulletList`, `taskList` | `tight`: `bool` | |
| `orderedList` | `start`: 0–999999999, `tight`: `bool` | `type`: `str` |
| `taskItem` | `checked`: `bool` | |
| `table` | `colCount`: non-negative `int` | |
| `tableHeader`, `tableCell` | `align`: `"left"`/`"center"`/`"right"`/`None`, `colspan`: `1`, `rowspan`: `1` | `colwidth`: list of `int` |
| `image` | `src` **(required)**, `alt`, `title`: `str` | `width`, `height`: `str` or `int` |
| `htmlBlock`, `htmlInline` | `html`: `str` | |
| `link` mark | `href` **(required)**, `title`: `str` | `target`, `rel`, `class`: `str` |

Every other type takes no attrs at all.
A name in neither column is an `unknown_attr` at both levels — that is the rule that stops an `onclick` from vanishing silently.
`bool` and `int` stay distinct: `{"level": True}` is refused rather than read as `1`.
Most of these also take `None`, meaning the attr was never set; the paragraph below says which do not.

> **Changed in 0.8.2** — a table cell's `colwidth` stays in `to_dict()` and `dump()`, as the other attrs in the right-hand column do; it used to be removed on input.

> **Changed in 0.7.0** — `strict` takes a level name instead of a bool, so `strict=True` now raises `TypeError`; `strict="exact"` is what it used to mean.
> Three things move with the new `"content"` level: the attrs in the right-hand column above are accepted and dropped rather than refused, `href`/`src` are required, and a refused presentation attr reports `unrepresentable` where it used to report `unknown_attr`.

> **Changed in 0.6.0** — `None` on the optional attrs above now means the attr is unset, and the key is dropped on the way in rather than coerced to `""`.
> Two things move with it: an `image` whose `alt` is `None` *and* which carries content children now renders that child text, and `to_dict()` omits such a key instead of echoing `""`.

`None` reads as unset wherever Tiptap declares `default: null`, which is most of the schema.
ProseMirror serializes every attr including defaults, so `None` is what the editor submits for an attr nobody filled in, and an unset attr is accepted already; the markdown is the same either way.
The exceptions are the settings Tiptap gives a non-null default — `level`, `start`, `tight`, `checked`, `colspan`, `rowspan` — plus `html`, which is marktip's own attr with no Tiptap counterpart.
Tiptap never emits a `None` for those, so one means the dict was built wrong; the conversion would survive it, and strict reports it because it is a bug rather than a loss.
`align` is unchanged: `None` was already a *value* there ("no alignment"), not an unset marker.

`href` and `src` are the one place a `None` is not "unset" but "missing", and both levels refuse it:

```python
tm.from_dict(link_without_href).to_markdown()   # '[a]()' — reads back as a real link
tm.from_dict(link_without_href, strict="content")  # InvalidNodeError: attr 'href' is required
                                                   # for mark type 'link'
```

A link with no destination is not a link, so writing `[a]()` is not a lossy conversion but an invented one, and the empty destination survives into stored Markdown.
An `href` of `""` is a different case and is accepted: that is what `from_markdown` itself produces for `[a]()`, and it round-trips exactly.
Rejecting an empty destination is the URI policy's job (`link_relative="reject"`).

`colspan`/`rowspan` are *known* attrs whose only accepted values are the no-ops Tiptap's table extension puts on every cell.
Refusing the names outright would leave strict unusable for the documents it exists to check.

The table's `colCount` is set to the widest row's cell count in either form.
In a schema without table tags, a body cell takes its column's header alignment.
With table tags, a body alignment that differs from the header selects tag output and is carried there.

## Extending the schema

Pass `schema=` to either input boundary to use declarations beyond the default GFM types.
Declarations are plain data: `MarkSpec` adds a mark, `NodeSpec` adds a node, and `core_attrs` adds attrs to a core type.
A callout has no official Tiptap shape, so declare the shape your editor uses:

```python
import marktip as tm

schema = tm.Schema(
    marks=[tm.MarkSpec("underline", tag="u")],
    nodes=[tm.NodeSpec(
        "callout", kind="block", content="block+",
        attrs={"tone": tm.Attr(str, choices=("note", "warning"), default="note")},
    )],
    core_attrs={
        "paragraph": {"textAlign": tm.Attr(str, choices=("left", "center", "right"))},
    },
)

source = '<callout tone="warning">\n\n<u>Read this</u>.\n\n</callout>'
doc = tm.from_markdown(source, schema=schema)
written = doc.to_markdown(canonical=True)
assert tm.from_dict(doc.to_dict(), schema=schema, strict="exact").to_markdown() == written
assert tm.from_markdown(written, schema=schema).to_dict() == doc.to_dict()
```

Every declared type has a tag form, with the type name as the default tag name.
Tag matching is exact and case-sensitive.
The content and `kind` determine its shape:

| Declaration | Shape | Written form |
| --- | --- | --- |
| `MarkSpec("underline", tag="u")` | mark | `<u>text</u>`, outside delimiter marks |
| `NodeSpec("mention", "inline")` | inline atom | `<mention/>` |
| `NodeSpec("ruby", "inline", content="inline*")` | inline container | `<ruby>inline content</ruby>` |
| `NodeSpec("embed", "block")` | block atom | `<embed/>` alone on its line |
| `NodeSpec("callout", "block", content="block+")` | block container | opening tag line, blocks, closing tag line |
| `NodeSpec("summary", "block", content="inline*")` | textblock | `<summary>inline content</summary>` as one paragraph |

`content=None` and `content=""` both declare an atom.
Inline atoms and inline containers can carry their own marks.
Marks open at a container's opening tag belong to the container node; its content starts with no open marks.
For example, `<u>a <ruby>x</ruby> b</u>` gives underline to `a `, the `ruby` node and ` b`, while `x` has no marks.
Marks opened inside the container apply only to its content.
A dict may give a container and its content marks of the same type independently.
Normalization removes equal delimiter marks (`bold`, `italic`, `strike` and `link`) from a container's content when the container already carries them.
The Markdown link form cannot represent a different link nested inside a container's link.
Declared mark tags and Markdown delimiter marks must open and close on the same side of each container boundary; crossing it raises `invalid_tag`.
The writer groups a marked container with adjacent nodes carrying the same marks and writes its content separately.
Mark order, delimiter placement and emphasis whitespace follow the inline atom rules.
A `code` mark on a declared inline atom or inline container is `invalid_mark_set` under strict validation, since the node cannot be written inside a code span.
With `strict="off"`, the node is written outside the code span and that mark is omitted.
Markdown-form headings use one line.
A heading with a hard break or newline uses its tag form when the schema provides it.
A soft newline in a textblock directly inside a table cell becomes a space in either table form.

> **Changed in 0.8.3** — an inline container carries its own marks, as an inline atom does.
> A mark around a container used to be moved onto the text inside it, so `to_markdown(canonical=True)` and an editor round trip wrote it inside the container tag.
> A mark crossing a container boundary used to be split and now raises `invalid_tag`.

### Attrs, exclusions and content

`Attr(type, required=False, choices=None, default=None, uri=None, inherit=False)` accepts `str`, `int`, `bool`, `tm.IntList` and `tm.StrMap`.
Integers fit in a signed 64-bit value; `bool` stays distinct from `int`.
`IntList` is a list of integers, written as a comma-separated attr such as `colwidth="100,200"`.
`choices` limits the allowed values, and `required=True` requires an attr after unset values have been removed.
An attr with `uri="link"` or `uri="image"` must be a `str` and cannot also declare a default.
It uses the corresponding URI policy and rejects control characters at every strict level.
`inherit=True` is for an attr of a declared mark, such as a style: see nested marks below.

`StrMap` groups string-valued tag attrs by prefix: `attrs={"data": tm.Attr(tm.StrMap)}` reads `data-hp="30" data-name="리안"` as `{"data": {"hp": "30", "name": "리안"}}`.
It works on marks, declared nodes and `core_attrs`, and any declared prefix can be used, including `aria`.
Map keys keep their spelling and order; they must be non-empty and contain only ASCII letters, digits, `_`, `:`, `.` or `-`.
Values use the same character-reference decoding, normalization and escaping as `str` attrs.
Map entries are written in their stored order, with the map placed among other attrs in declaration order.
An empty map or `None` is unset and omitted; `required=True` requires at least one entry.
`StrMap` does not accept `choices`, `default` or `uri`.
An owner cannot declare both a `StrMap` named `X` and another attr whose name starts with `X-`.
The bare tag attr `X="..."` is `unknown_attr`; only `X-key="..."` supplies a map entry.
Collecting Tiptap editor attrs into the map is the editor's responsibility.

> **Changed in 0.8.2** — `tm.StrMap` is new.

`None` means unset.
A value equal to its declared `default` also means unset: the key is removed on input, never written, and never filled back in, including under `strict="exact"`.
Compare a round trip with `from_dict(original, schema=schema).to_dict()`, not the unnormalized input dict.
ProseMirror can restore its own defaults when it loads the result.

Declared tag attrs are written in declaration order and always double-quoted.
`&`, `"`, `<`, `>`, `|`, the backtick and C0 controls are written as character references.
The reader accepts double-quoted, single-quoted, unquoted and value-less boolean attrs, decodes character references, and checks the declared type.
An undeclared attr on a declared tag is `unknown_attr`; a repeated attr is `invalid_attr_value`.
Dict input under `strict="off"` skips declared attr and content validation when reading the submitted tree.
If normalization removes a child and cannot fill the required content, it raises `invalid_content` at every strict level.
Writing omits attrs the declaration does not carry.

`MarkSpec.excludes=None` means the mark excludes its own type, `()` excludes nothing, and `"_"` excludes every mark.
Otherwise pass a tuple of mark names.
Two marks conflict if either excludes the other; both strict dict levels and the Markdown reader report `invalid_mark_set`.
Opening conflicting declared tags is an error even when their overlap contains no inline content.
A self-exclusive mark nested inside itself replaces the outer mark for its extent and restores it afterward.
The replacing mark keeps the outer mark's attrs declared with `inherit=True`, except those its own tag writes.
With `TEXT_STYLE`, `<span color="red">a <span fontSize="12px">b</span></span>` gives `b` both `color` and `fontSize`,
and `<span color="blue">` inside it would override the color.
An attr without `inherit=True` is not carried over, and only reading Markdown is affected:
`to_markdown()` writes each run as one flat tag with all of its attrs.
For `StrMap`, inheritance copies the whole outer map when the inner tag has no entries for that prefix.
An inner map replaces it as a whole; keys are not merged.
Mark replacement and attr inheritance stop at inline container boundaries.
A mark inside a container cannot inherit attrs from a mark outside it, including attrs declared with both `required=True` and `inherit=True`.
Those required attrs must be supplied inside the boundary.

> **Changed in 0.8.3** — a mark tag inside an inline container no longer inherits from a mark outside it.

> **Changed in 0.8.2** — an attr declared with both `required=True` and `inherit=True` is satisfied by the value it inherits.
> The inner tag used to raise `missing_attr` before inheritance.

> **Changed in 0.8.1** — `Attr(inherit=True)` is new, and the `TEXT_STYLE` preset declares its attrs with it:
> a nested `<span>` now keeps the outer span's styles, as Tiptap's TextStyle does when it reads HTML.
> Pass `text_style(merge_nested_span_styles=False)` for the previous behavior.
> A schema that uses `TEXT_STYLE` has a new fingerprint, so documents stored with it by 0.8.0 are read without their source spelling.
A mark with `excludes=()` can stack with a different instance of its own type; equal type and attrs still count as a duplicate.

Content expressions use ProseMirror's grammar: node names, group names, sequences, `|`, `*`, `+`, `?`, `{n}`, `{n,}`, `{n,m}` and parentheses.
The built-in groups are `inline` and `block`.
A node joins the group matching its kind by default; `group="name"` replaces that membership, `group="a b"` joins both, and `group=""` joins none.
An expression cannot mix inline and block members or give an inline node block content.
Use `text*` or `text+` for text runs: expressions that count adjacent `text` or `htmlInline` nodes are refused because Markdown merges those nodes.

The schema compiles expressions once when it is built.
Strict dict conversion checks the submitted children first.
Markdown input can create missing required children when a type has no required attr and its own minimal content can be created.
After empty blocks are normalized, dict input uses the same fill rules for required children.
Only `paragraph` can be created among core types; `text` cannot be created.
Where several types fit, the first type named by the expression wins, and a fill that would create its own ancestor is refused at schema construction.
Whether an empty paragraph survives also depends on the schema's paragraph tag and its position in the tree.

An implicit wrapper is a block node declared with `implicit=True` and `group=""`.
It writes only its children; the reader wraps a run the parent does not accept directly.
It must have block content, no attrs and no tag.
Its content may not name another implicit node.
Each parent expression must name it exactly once, without optionality or repetition.
Its accepted child types must be disjoint from the parent's direct types and from the contents of any other implicit child of that parent.
The `DETAILS` preset uses this for Tiptap's `detailsContent` node.

### Fence and math carriers

A block atom can declare `fence="math", body="latex"` with a declared `str` attr named `latex`.
A code block whose effective info (`language`, otherwise `info`) has the declared word as its first word reads as the declared type.
The reader uses only the first word for a declared carrier.
For example, the suffix in `math display` is omitted from the declared node and its canonical spelling.
A leading tab prevents the info from selecting a declared carrier.
The code body loses its final newline; writing adds one newline.
When md4c reads a code block or a declared fence carrier, it expands tabs in the leading indentation to spaces.
Tabs after the leading indentation are kept.
The fence form is used only when the body attr is set, no other attr is set, the body has no carriage return, and no line's leading whitespace contains a tab.
Otherwise the node uses its tag form, so an unset body and an empty body remain distinct.
Strict dict input refuses a core `codeBlock` whose info word collides with a declared fence, with `unrepresentable`.

An inline atom can declare `math="inline", body="latex"` to read `$...$`.
A block atom with `math="display"` reads a paragraph made only of `$$...$$`; display math is written as its fence form if declared, otherwise as a tag.
Declaring either math mode makes `$` syntax for that schema, so existing unescaped dollar pairs can become math.
The writer escapes dollar signs in ordinary text and image alt text.
A span of an undeclared mode becomes literal text with its delimiters, and its inside is not parsed as Markdown.

Inline math uses `$body$` only when its body and surrounding output prove that it reads back as the same node.
Empty bodies, line breaks, dollar signs, backticks, odd trailing backslashes, word adjacency and a pipe in a Markdown table cell select the tag form.
A math node whose body contains `*`, `~`, `[` or `]` also uses its tag form when it carries marks or sits inside a container carrying a delimiter mark.
The body of the dollar form is written raw.

### Core tag forms

`core_attrs` can add attrs to `paragraph`, `heading`, `image`, `link`, `blockquote`, the list family, and the table family.
An attr Markdown already carries, such as `href` or `level`, cannot be redeclared.
Known dropped attrs such as link `target` or image `width` can be redeclared with one type; `required=True` is refused for every `core_attrs` declaration.
Without a redeclaration, a dropped attr stays dropped in either form and keeps its existing strict behavior.

| Core type | Active tag form |
| --- | --- |
| `paragraph`, `heading` | `<p>`, `<h1>` through `<h6>` |
| `image`, `link` | `<img/>`, `<a>` |
| `blockquote` | `<blockquote>` |
| `bulletList`, `taskList`, `orderedList` | `<ul>`, `<ol>` |
| `listItem`, `taskItem` | `<li>`, `<li checked="...">` |
| `table`, `tableRow`, `tableHeader`, `tableCell` | `<table>`, `<tr>`, `<th>`, `<td>` |

A set overlay attr selects the tag form.
A kept empty paragraph also uses its available tag, except for a sole filler paragraph in a list item, task item, table cell or blockquote.
A heading with a hard break, a newline in text, or a newline in an inline HTML payload uses its available tag too.
A heading directly in a pipe cell uses its tag whenever the schema provides it.
Declaring attrs on any list or table type activates its whole family.
A list uses tags when it or any item needs them; items follow the list's form.
A table uses tags when header cells are not exactly its first row, when rows have different cell counts, or when a body cell's alignment differs from its header's.
A cell with several children, a child the pipe form cannot carry, or a set overlay on the table, a row or a cell also selects table tags.
Rows and cells follow the table's form.
A pipe cell can carry a paragraph, a lone block image, a block atom or a supported textblock tag.
An empty list or rowless table is removed in either form.

An active table family can carry multiple blocks and block containers in a cell; the Markdown form cannot.
Declaring `colspan` and `rowspan` carries merged cells, and `colwidth` can use `tm.IntList`.
Undeclared unit spans stay stored on dict input but are omitted from a cell tag, as they are from Markdown.
A core tag writes Markdown-carried attrs first in syntax order (`src`, `alt`, `title` for images; `href`, `title` for links), followed by overlay attrs in declaration order.
Heading level is carried by its tag name.

Declared tags exposed as tag constructs are syntax with either `html=True` or `html=False`.
With `html=True`, declared-looking tags inside an undeclared HTML block or a comment stay part of that raw construct.
An unmatched tag, wrong placement, invalid attr, conflicting mark set or invalid content is an error, not a raw-HTML fallback.
Marks around a lone declared block tag are `invalid_mark_set`, since a block tag cannot carry those marks.
This includes hand-written HTML tables and lists once their family is active: each container tag must occupy its own block line and its children must fit the content model.
`<table>\n<tr><td>a</td></tr>\n</table>` is not a substitute for that form.
Strict dict input also refuses raw HTML payloads that would be read as declared tags, with `unrepresentable`.

### Presets and schema ownership

The presets are declarations, not precompiled schemas:

| Presets | Value |
| --- | --- |
| `UNDERLINE`, `HIGHLIGHT`, `SUBSCRIPT`, `SUPERSCRIPT`, `TEXT_STYLE` | `MarkSpec` |
| `MENTION`, `INLINE_MATH`, `BLOCK_MATH` | `NodeSpec` |
| `DETAILS` | tuple of three `NodeSpec`s |
| `TEXT_ALIGN`, `LINK_ATTRS`, `IMAGE_SIZE`, `TABLE_SPANS` | mappings for `core_attrs` |

```python
editor_schema = tm.Schema(
    marks=[tm.UNDERLINE, tm.HIGHLIGHT, tm.SUBSCRIPT, tm.SUPERSCRIPT, tm.TEXT_STYLE],
    nodes=[tm.MENTION, *tm.DETAILS, tm.INLINE_MATH, tm.BLOCK_MATH],
    core_attrs={
        **tm.TEXT_ALIGN,
        **tm.LINK_ATTRS,
        **tm.IMAGE_SIZE,
        **tm.TABLE_SPANS,
    },
)
```

`HIGHLIGHT` declares an optional `color`, so it accepts highlights from editors with or without multicolor enabled.
`DETAILS` declares `open` with default `False`, accepting both persisted and non-persisted open-state JSON.
`TEXT_ALIGN` follows Tiptap's documented configuration for `heading` and `paragraph`; use `text_align(types=...)` for other targets.
`IMAGE_SIZE` adds size attrs to images in either shape.
The default shape matches `Image.configure({inline: true})`; use `block_image=True` for Tiptap's stock block-image shape.
The configurable functions mirror options that change Tiptap's JSON:

| Factory | Default declaration |
| --- | --- |
| `text_style(...)` | `background_color`, `color`, `font_family`, `font_size` and `line_height` are all `True`, matching TextStyleKit; `merge_nested_span_styles=True` matches TextStyle's `mergeNestedSpanStyles` and declares each attr with `inherit=True` |
| `text_align(types=..., alignments=..., default_alignment=...)` | `("heading", "paragraph")`; `("left", "center", "right", "justify")`; `None` |
| `link_attrs(target=..., rel=..., class_=...)` | `"_blank"`; `"noopener noreferrer nofollow"`; `None` |

Each uppercase constant equals its declaration in the shared preset data file.
Two overlays for the same core type should be combined with `Schema.extend`, which merges per type rather than replacing the entire owner mapping.

A schema is selected per call, immutable after compilation, and shareable between threads.
Treat declaration objects and their attr mappings as frozen after using them to build a schema.
The document keeps its schema for serialization; it belongs to the schema that wrote it.
Reading stored Markdown with a different schema may leave old tags as raw HTML, interpret new syntax, or raise a validation error.
Store the schema declaration or its application-level identifier with the Markdown.

```python
import json

saved = json.loads(json.dumps(schema.to_dict()))
restored = tm.Schema.from_dict(saved)
assert restored == schema
assert hash(restored) == hash(schema)

extended = schema.extend(marks=[tm.MarkSpec("comment", attrs={"id": tm.Attr(str, required=True)}, excludes=())])
assert extended != schema
```

`extend` returns a new schema and refuses duplicate declarations, including the same attr declared twice for one core type.
Equality and hashing compare declarations in order, not just the languages they accept: an omitted tag and an explicit tag equal to the type name differ.
Compilation happens once per schema object, so reuse a schema when calls share the same editor configuration.
In an earlier measurement on an Intel Core Ultra 9 185H Linux machine with Python 3.14.6 and a GCC 16.2.1 Release build,
`scripts/benchmark.py` measured about 61 microseconds to build a schema with five marks, six nodes and attrs for six core types.
That is the best of seven batches of 1,000 builds, with declarations prepared outside the timed work.

### Block images

Tiptap's Image extension defaults to block images.
Choose that shape with `Schema(block_image=True)`:

```python
image_schema = tm.Schema(block_image=True, core_attrs=tm.IMAGE_SIZE)
image_json = {"type": "doc", "content": [
    {"type": "image", "attrs": {"src": "logo.png", "alt": "Logo", "width": 160}},
]}
image_doc = tm.from_dict(image_json, schema=image_schema, strict="exact")
assert tm.from_markdown(image_doc.to_markdown(), schema=image_schema).to_dict() == image_doc.to_dict()
```

The existing `image` type then belongs to the block group instead of the inline group.
It can be a document, blockquote, list-item or table-cell child; strict conversion refuses it inside a paragraph or other inline content and refuses a `marks` field on it.
Without the option, the existing inline-image grammar is unchanged.
A block image writes ordinary image Markdown on its own line,
or a standalone `<img .../>` when a declared overlay attr is set.
It also fits a Markdown table cell's one-line form.
Inside a list item, a Markdown-form block image needs no blank line next to a paragraph or another image; elsewhere blocks are separated as usual.
The option changes only the image's shape.
`<img>` is declared syntax only when `core_attrs` activates the image tag form; otherwise it remains raw HTML or literal text under the `html` option.

On Markdown input a paragraph containing only an image becomes that image.
A paragraph with a set overlay attr and no surviving paragraph fragment is `invalid_content`, so the overlay is not silently discarded when it holds only images.
A paragraph with text beside an image splits into paragraphs and block images,
trimming whitespace and hard breaks at each cut and omitting fragments left empty.
An image in a heading or beside other content in a Markdown table cell is `invalid_content`.
An image carrying any mark, including a link, is `invalid_mark_set`; marks are never silently discarded.
Only paragraphs split, and active inline `<img .../>` tags follow the same rules.
The URI policy, `reject_node_types` and `IMAGE_SIZE` work in either image shape.

`block_image` is part of schema persistence and identity; `to_dict()` includes the key only when it is true.
`extend()` inherits the option unless `block_image=True` or `block_image=False` is supplied explicitly.

## Errors

Document rejections derive from `marktip.MarktipError`, so "the input is malformed" is a single `except`:

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
| `max_depth` | `InvalidNodeError` | dict nesting exceeds 512 |
| `disallowed_scheme` | `InvalidNodeError` | a core or declared URI attr has a scheme outside its allowlist |
| `disallowed_relative_url` | `InvalidNodeError` | a scheme-less core or declared URI attr violates its relative policy |
| `invalid_uri_char` | `InvalidNodeError` | a core or declared URI attr contains an ASCII control character |
| `disallowed_node_type` | `InvalidNodeError` | a node type appears in `reject_node_types` |
| `unknown_field` | `InvalidNodeError` | `strict`: a node/mark top-level key is not defined for that type |
| `invalid_content` | `InvalidNodeError` | a content-model violation on strict dict input or a declared tag, a required child that cannot be filled after normalization, or an invalid strict text payload |
| `unknown_attr` | `InvalidNodeError` | an unknown attr on strict dict input or a declared tag |
| `invalid_attr_value` | `InvalidNodeError` | a wrong type, out-of-range value or repeated tag attr |
| `unrepresentable` | `InvalidNodeError` | well-formed input would lose content or attrs in the selected Markdown form, including emphasis the writer's spelling cannot carry |
| `missing_attr` | `InvalidNodeError` | a required attr is unset on strict dict input or a declared tag |
| `invalid_mark_set` | `InvalidNodeError` | conflicting or duplicate marks on strict dict input or in declared tags |
| `invalid_tag` | `InvalidNodeError` | a declared tag is unmatched, self-closing where a container is required, or in the wrong position; a declared or delimiter mark crosses an inline container boundary |
| `markdown_max_depth` | `ParseError` | Markdown node nesting or simultaneously open declared mark tags exceeds 512 |
| `parse_failed` | `ParseError` | MD4C could not parse the input |

Malformed schema declarations are caller bugs and raise ordinary Python exceptions rather than `MarktipError`; bad declaration values raise `ValueError`.
`from_markdown` raises a plain `TypeError` when the argument is not `str`/`bytes` for the same reason.
Bad option values behave similarly: a non-iterable `link_schemes` or `reject_node_types` raises `TypeError`, and `link_schemes=("https://",)`, `reject_node_types=("callout",)`, `link_relative="nope"` or `strict="strict"` raises `ValueError`.
`strict` takes a level name, so `strict=True` raises `TypeError` rather than quietly meaning something.

> **Changed in 0.4.0** — these were previously `ValueError` (`from_dict`) and `RuntimeError` (`from_markdown`).
> `MarktipError` derives from `Exception` directly, so `except ValueError` no longer catches them.

> **Changed in 0.7.0** — `missing_attr` is new, and an attr with no markdown form now reports `unrepresentable` rather than `unknown_attr`, which is left meaning "no schema declares this name".
> `attrs` values that are not `str`/`int`/`bool` are dropped instead of stringified, so `to_dict()` no longer echoes a `"[1, 2]"` the caller never wrote.

> **Changed in 0.5.0** — an ASCII control character in a link `href` or image `src` is now rejected outright, with or without the URI policy.
> A URI cannot carry one unencoded (`%09` is the encoded form), and leaving it in would defeat the allowlist itself, because browsers strip tab/LF/CR before reading the scheme.
> This also rejects `[x](<a\tb>)`, which CommonMark otherwise accepts.

> **Changed in 0.5.0** — an `orderedList` `start` outside 0–999999999 is clamped instead of emitted verbatim, and a code fence `language` is truncated at the first newline.
> Both previously produced output that reparsed into a different document; see [Defined normalizations](#defined-normalizations).

## What `from_dict` validates

The selected schema is closed: every node/mark type must have a Markdown or tag mapping.
`from_dict` rejects unknown types instead of silently dropping content.
The following checks apply to the submitted tree.

- **Closed schema.**
  Node types are `doc`, `paragraph`, `text`, `hardBreak`, `heading`, `blockquote`, `codeBlock`, `horizontalRule`, `bulletList`, `orderedList`, `listItem`, `taskList`, `taskItem`, `table`, `tableRow`, `tableHeader`, `tableCell`, `image`, `htmlBlock`, `htmlInline`.
  Marks are `bold`, `italic`, `strike`, `code`, `link`.
  Additional types must be declared in the passed schema; anything else raises `UnknownTypeError`.
- **`type` is required** on every node and mark.
- **The root is a `doc`.**
- **Shapes**: `attrs` is a dict, `content` and `marks` are lists, and every entry of `content`/`marks` is a dict.
  With `strict="off"`, an explicit `None` for `attrs`, `content` or `marks` is read as an absent key.
- **Depth** is at most 512 levels.
  The same limit caps simultaneously open declared mark tags.
- **No ASCII control character** in a link `href` or image `src`, entity references included (`&Tab;`, `&#09;`).
- **The URI policy**, when `link_schemes`/`image_schemes`/`link_relative`/`image_relative` ask for it — see [Restricting link and image URIs](#restricting-link-and-image-uris).
- **The node-type policy**, when `reject_node_types` names a type.
  Normalization adds required fillers after this check. [Rejecting node types](#rejecting-node-types)

`from_markdown` applies the same URI and node-type policies to the parsed tree before normalization.

It deliberately does **not** validate, unless `strict` asks it to:

- **`attrs` names and value types.**
  Keys are free-form.
  `str`, `int` and `bool` can be stored on free-form keys; a list of integers is stored only for an attr declared `tm.IntList` and for a table cell's `colwidth`.
  A dict is stored only for an attr declared `tm.StrMap`, with string keys and values and valid map keys as described above.
  With strict validation off, any invalid key or non-string value drops the whole map.
  Both strict levels report `invalid_attr_value` for a non-dict map value or an invalid map entry.
  Other values and `None` are dropped.
  Declared defaults are also removed.
  An attr with no markdown form is dropped at serialization — see [Refusing lossy conversions](#refusing-lossy-conversions).
- **Per-node required attrs.**
  A `heading` without `level` gets the default level during normalization.
  A `codeBlock` can omit `language` and `info`.
  For core types `strict` requires a link's `href` and an image's `src`, because an empty destination would read back as a real link.
  Declarations can require additional attrs on declared types.
  `{"src": None}` and no `src` key at all are both missing values for validation and the URI policy.
  Inheritance distinguishes them: an absent key can borrow a matched base value, while `None` cannot.
- **Mark sets.**
  With strict validation disabled, two marks of the same type may appear on one node and are serialized independently.
  Both strict levels enforce the selected schema's exclusions and reject equal type-and-attr duplicates.
- **Node and mark top-level fields.**
  With strict validation disabled, a key the converter does not read is ignored.
  Both enabled levels reject it with `unknown_field`, including `marks` on a block or `text` on a non-text node.
- **Content models.**
  With strict validation disabled, the submitted tree's content model is unchecked, so a `text` node directly under `doc` is accepted and serialized.
  Both enabled levels enforce the content-model table above, the text payload shape, and the absence of marks inside a code block.
  After normalization removes a child, a required child that cannot be filled raises `invalid_content` at every strict level.
- **Raw HTML.**
  The URI policy governs link/image and declared URI attrs, not undeclared markup inside `htmlBlock`/`htmlInline`.
  Without an active link tag form, `<a href="javascript:...">` remains raw HTML and passes it.
  Reject those node types with `reject_node_types=("htmlBlock", "htmlInline")`; on Markdown input, `html=False` is the alternative that retains the markup as literal text.
- **URI syntax beyond the scheme.**
  Everything after the scheme is opaque.
  Dict URI values are not rewritten; core Markdown destinations are checked entity-decoded, and active tag forms also check the stored form.
  A tag attr is entity-decoded when read into the document.
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

marktip preserves non-whitespace characters in order, including punctuation.
Code, images, math and raw HTML count as units of content.
Normalization preserves marks on letters and digits, including link destinations and declared mark attrs.
It preserves the textblock kind and heading level, the item, quote or cell containing the content, and the list kind and checked state.
Whitespace and punctuation here follow md4c's delimiter classification.

Whitespace, emphasis on whitespace and punctuation, and the header status of a pipe table's first row are normalized as described below.
Node boundaries, mark order, attr defaults, fillers and the final fence newline can also change.
Attrs such as an undeclared link `target` or image `width` can stay in the tree while being omitted from Markdown under strict content.
Use `strict="exact"` to require those attrs in the output.

### What the inputs normalize

These rules run after reading and policy checks, before matching a dict input against its base.
The writer uses the resulting tree when it needs to regenerate a block.

- **Characters and line edges** — CR and CRLF in text become LF.
  Paragraphs and headings trim spaces, tabs and newlines at line edges, including after a hard break, regardless of their form or link and tag marks.
  Repeated soft newlines collapse, and a soft newline after a hard break is removed.
  A soft newline before a hard break is kept when the textblock can carry both.
  Declared textblocks preserve whitespace at their outer tag boundaries.
  Code-marked text keeps its spaces and changes internal newlines to spaces.
- **Hard breaks** — leading hard breaks stay, and trailing runs of hard breaks in paragraphs are removed in every form, including in cells.
  A hard break loses its code mark and keeps the break itself.
  In a heading, hard breaks and newlines use the heading tag if the schema provides one.
  Without that tag, they become spaces.
  Soft newlines in textblocks directly inside table cells become spaces in either table form.
- **Mark order** — continuing marks keep their outside position, with continuation judged by mark type.
  Newly opened core marks are ordered link, strike, italic, bold and then code.
  Declared marks follow declaration order, and links written as tags follow the other core marks.
- **Runs and inline containers** — adjacent text or raw-inline-HTML nodes with equal marks join.
  Equal delimiter marks on an inline container and its content stay on the container alone.
  A nested self-exclusive mark replaces the outer one until the inner mark ends.
  Within the same inline container, a declared inner mark keeps attrs marked `inherit=True`.
- **Emphasis edges** — bold, italic and strike are removed from edge whitespace and punctuation where their delimiters cannot open or close under md4c's rules.
  A hard break at an emphasis edge loses the emphasis, including where md4c could open it.
  Link and tag marks remain.
  For example, the trees `a**"b"**c` and `**Note:**text`, shown in Markdown notation, write as `a"**b**"c` and `**Note**:text`.
  Edge cleanup and run joining repeat until the tree stops changing.
- **Empty blocks and fill** — empty list items, task items, table cells and blockquotes receive one empty paragraph.
  A sole empty document paragraph is removed.
  Other empty paragraphs are removed unless the schema provides a paragraph tag or a required child has to be filled.
  Lists with no items and tables with no rows are removed in every form.
  Declared nodes fill required children after these adjustments.
- **Lists** — a missing `tight` becomes `true`.
  A loose list with a single item that writes one block becomes tight, and a tight list whose item needs a blank line becomes loose.
  These rules apply in Markdown and tag forms.
  An LI with `checked` is a task item, including when the value is false.
  A UL containing any task item becomes a task list and its unchecked items become unchecked task items.
  Each LI's attrs are decoded against the type selected by its own `checked`.
- **Tables** — without table tags, the first row becomes the header, subsequent rows become body rows, and body cells take the header alignment.
  Multiple paragraphs without tag attrs in a cell join with hard breaks.
  Under `strict="off"`, this join also applies to paragraphs with tag attrs and can drop those attrs.
  Short rows are padded with empty cells.
  With table tags, differing row lengths and body alignments are carried in tags.
  In either form `colCount` is the widest row's cell count, which can be smaller than the visual width with spanning cells.
- **Core attrs** — fill the defaults for heading `level`, ordered list `start`, task `checked` and image `alt`.
  Heading levels clamp to 1–6 when input validation permits an out-of-range value.
  Images discard children.
  Empty link and image titles and empty `language` and `info` are omitted.
  For a code block, the first fence info word supplies `language`.
  If a supplied language disagrees with that word, it replaces the info string.
  Fence info and language are truncated at the first newline when accepted from permissive dict input.
  md4c trims spaces before the language, so a leading tab can leave `info` set with no language.
  The same word rule applies when choosing a declared fence carrier.
- **Other text and attrs** — NUL in text and non-URI string attrs becomes U+FFFD.
  On Markdown input this happens before tokenization, including for code and raw HTML.
  URI attrs containing a NUL raise `invalid_uri_char`.
  Declared defaults and `None` are omitted, except where an attr such as cell `align` treats `None` as a value.
  Line breaks inside math spans become spaces, and display math read as a block has its outer whitespace trimmed.
- **Block-image paragraphs** — with `block_image=True`, a block image splits its paragraph.
  Whitespace and hard breaks at the cuts are removed, and empty fragments are dropped.
  A fragment beginning with a line such as `<div class="caption">Caption</div>` can read back as an HTML block.

### What the writer carries

- Hard breaks use a backslash followed by a newline, or `<br>` in a pipe cell.
  Code spans containing only spaces are written without padding.
- A paragraph's second line is escaped if its first nonblank character is `|` or `:`.
  Line-start escapes leave raw inline HTML payloads alone.
  A supplied payload whose later line starts a Markdown block can therefore read back as separate blocks.
- Text that looks like a URL, email address or `www.` link is escaped where md4c would start an enabled autolink.
  Text under a Markdown link and image alt text need no autolink escape.
  A backtick in a link destination is escaped, and an empty destination with a title is written as `<>`.
- Code fences write the full info string.
  A backtick in the info string selects a tilde fence.
  The writer always adds a newline after the body, even for an empty fence.
  The reader removes that one newline from the stored code text.
- Loose lists use a blank line between blocks inside each item.
  An ATX heading, a fenced `codeBlock` or a thematic break can be followed by another block without a blank line.
  A thematic break inside an item uses underscores.
  Other combinations still need separation, including a heading, code fence or block tag after a pipe table and a non-1 ordered sublist after a paragraph or Markdown-form image.
  The writer can add a blank line where md4c would keep the blocks separate, for example between a declared fence carrier and a textblock.
  A task item with a non-paragraph first block starts with the checkbox on its own line, which reads without an extra leading paragraph.
  Continuations use the list marker's indent without the checkbox width.
- Adjacent lists alternate markers to stay separate.
  Ordered list markers stay within CommonMark's 0–999999999 range, and the running number stops at that ceiling.
  Only the first number of a list is read back.
- A kept empty paragraph uses `<p></p>` when the schema provides that tag, including inside a declared container.
  A sole empty filler in a list item, task item, table cell or blockquote writes nothing.
  A heading directly in a pipe cell uses its tag when the schema provides it.
  Undeclared unit spans remain in the tree and are omitted from table tags and pipe tables.

### What strict refuses

Under `strict="content"` and `strict="exact"`, an emphasis or pipe-cell refusal raises `InvalidNodeError` with code `unrepresentable` and the input path.
The paragraph-join check runs while reading the dict.
The remaining pipe-cell checks and the emphasis check run after inheritance and skip blocks that inherited remembered source.
`strict="off"` is outside the round-trip guarantees.

- **Emphasis** — strict dict input reads back each textblock carrying bold, italic or strike in a block without remembered spelling.
  The writer uses one spelling, with `*`, `**` and `~~` nested in stored mark order.
  If the inline content reads back differently, strict refuses it.
  Examples include some overlapping marks on touching words and emphasis that starts or ends at a link's edge against a letter.
  Some such trees have another spelling marktip does not search for.
  `from_markdown` skips this check.
- **Pipe cells** — in a schema without table tags, strict refuses blocks that a one-line cell would flatten, such as a heading without a heading tag.
  A lone block image, declared block atom or supported textblock tag can be carried.
  A declared or tag-form block container is refused.
  A declared or tag-form non-paragraph block that can be carried must be the cell's only child.
- **Paragraph joins in pipe cells** — strict checks the submitted attrs before inheritance.
  If the cell contains paragraphs that would be joined, a paragraph with a tag attr is refused at its input path.

On `make_fixture(1200, 4)` from `scripts/benchmark.py`, emphasis read-back averaged about 80,000 instructions per emphasized textblock.
On the same fixture, `from_dict(..., strict="content")` without a base went from 833 million instructions per call in 0.8.3 to 1,238 million in 0.9.0.
The counts are user-space instructions measured on an Intel Core Ultra 9 185H running Linux x86_64 with CPython 3.14.10 and a GCC 16.2.1 Release build.
Each per-call figure is the best of five calls.

## JavaScript package

The `marktip` ES module runs the same C++ core through WebAssembly.
It provides the Python document and schema APIs, with TypeScript declarations.
Tiptap JSON, stored documents and schema dicts have the same shape in both languages, so either language can read what the other stores.
The package is built for bundlers and direct ES module use.
Unbundled use needs a runtime that can import JSON modules with `with { type: "json" }`.
The automated tests run on Node.
The package was also run by hand in Firefox 160: bundled with Vite on the main thread and in a module worker, and as direct ES modules.
Other browsers have not been tried.

### Building the package

From the repository root, with CMake, Ninja, Emscripten 6.0.13, Python, Node 26 and TypeScript 6.0.3 (`tsc`) installed:

```bash
EM_CACHE="$PWD/build-wasm/cache" emcmake cmake -S . -B build-wasm -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DMARKTIP_BUILD_PYTHON=OFF -DMARKTIP_BUILD_WASM=ON
EM_CACHE="$PWD/build-wasm/cache" cmake --build build-wasm
python js/build.py
```

`EM_CACHE` keeps Emscripten's generated system libraries inside the build directory when its default cache is not writable.
The first build may take a few minutes while those libraries compile.
The package build uses the global TypeScript compiler and needs no npm dependencies.
It produces `js/dist/` with JavaScript, declarations, the Emscripten module and `.wasm`, presets and licence texts.
The preset data comes from the same `python/marktip/presets.json` used by Python.

The examples below use the package entry point `marktip`.
For a local build, import `./js/dist/marktip.js` from the repository root.

### Parsing a stream

Call `await tm.init()` once before constructing schemas or documents.
Every subsequent conversion is synchronous.
Pass the complete text received so far on each update; marktip reparses it on each call.

```ts
import * as tm from "marktip";
await tm.init();

const schema = new tm.Schema({
  marks: [tm.UNDERLINE],
  nodes: [{
    name: "callout", kind: "block", content: "block+",
    attrs: { tone: { type: "str" } },
  }],
});

const text = '<callout tone="note">\n\nHello';
const doc = tm.fromMarkdown(text, { schema, partial: true, keepSource: false });
render(doc.toDict());
doc.free();
```

`partial` has the [same limits as in Python](#usage): incomplete tags are text and can temporarily violate a narrow content model.
A streaming caller can keep its last successful result while `invalid_content` lasts.

### Storage and editing

Keep the remembered spelling in `dump()`, then supply a loaded document as `base` when accepting edited Tiptap JSON:

```ts
const original = tm.fromMarkdown("Title\n=====\n\n* first\n", { schema });
const stored = original.dump();
original.free();

const base = tm.load(stored, { schema });
const editorJson = base.toDict();
const edited = tm.fromDict(editorJson, { schema, base, strict: "exact" });
const saved = edited.dump();
const markdown = edited.toMarkdown();
const canonical = edited.toMarkdown({ canonical: true });
base.free();
edited.free();
schema.free();
```

`toDict()` and `dump()` return ordinary values for `JSON.stringify` or editor input.
`fromDict()` and `load()` accept ordinary JSON-compatible values.
A document keeps its schema alive even after the schema's handle is freed.
Use `edited.equals(base)` to compare the trees before replacing an editor's contents.

### API correspondence

Defaults and conversion rules match Python's.
Unknown option names raise `TypeError`, including snake_case names passed to camelCase options.
`Schema.fromDict()` reads the stored dict form, where `core_attrs` and `block_image` retain their snake_case spelling.

| Python | JavaScript |
| --- | --- |
| `from_markdown(md, cjk_friendly=, html=, partial=, keep_source=, schema=)` | `fromMarkdown(md, { cjkFriendly, html, partial, keepSource, schema })` |
| URI and node options: `link_schemes`, `image_schemes`, `link_relative`, `image_relative`, `reject_node_types` | `{ linkSchemes, imageSchemes, linkRelative, imageRelative, rejectNodeTypes }` on `fromMarkdown` or `fromDict` |
| `from_dict(ast, ..., cjk_friendly=, strict=, schema=, base=)` | `fromDict(ast, { ..., cjkFriendly, strict, schema, base })` |
| `load(data, schema=)` | `load(data, { schema })` |
| `doc.to_dict()`, `doc.dump()`, `doc.to_markdown(canonical=)` | `doc.toDict()`, `doc.dump()`, `doc.toMarkdown({ canonical })` |
| `a == b` for documents | `a.equals(b)` |
| `Schema(marks=, nodes=, core_attrs=, block_image=)` | `new Schema({ marks, nodes, coreAttrs, blockImage })` |
| `schema.marks`, `.nodes`, `.core_attrs`, `.block_image` | `schema.marks`, `.nodes`, `.coreAttrs`, `.blockImage` |
| `schema.to_dict()`, `Schema.from_dict(data)`, `schema.extend(...)`, `a == b` | `schema.toDict()`, `Schema.fromDict(data)`, `schema.extend({ ... })`, `a.equals(b)` |
| `UNDERLINE`, `HIGHLIGHT`, `SUBSCRIPT`, `SUPERSCRIPT`, `TEXT_STYLE`, `MENTION`, `DETAILS`, `INLINE_MATH`, `BLOCK_MATH`, `TEXT_ALIGN`, `LINK_ATTRS`, `IMAGE_SIZE`, `TABLE_SPANS` | Same names; `DETAILS` is an array |
| `text_style(background_color=, color=, font_family=, font_size=, line_height=, merge_nested_span_styles=)` | `textStyle({ backgroundColor, color, fontFamily, fontSize, lineHeight, mergeNestedSpanStyles })` |
| `text_align(types=, alignments=, default_alignment=)` | `textAlign({ types, alignments, defaultAlignment })` |
| `link_attrs(target=, rel=, class_=)` | `linkAttrs({ target, rel, class })` |
| `MarktipError`, `UnknownTypeError`, `InvalidNodeError`, `ParseError` | Same names, hierarchy and fields: `code`, `path`, `detail`, plus `type`/`kind` or `field` |
| `__version__` | `version`, available after `init()` |

`Schema.extend()` returns a new schema, appends marks and nodes, and merges core attrs per owner.
A duplicate core attr is an error.
`equals()` compares declarations in order, so reordering attrs changes equality.

The differences from Python are:

1. Names use camelCase and keyword arguments become one options object.
2. Initialization requires one `await tm.init()`; subsequent calls are synchronous.
3. `Document` and `Schema` have `free()` and also register for automatic cleanup with `FinalizationRegistry`.
   A method called after `free()` raises a clear error; calling `free()` twice does nothing.
4. `MarkSpec`, `NodeSpec` and `Attr` are types for plain objects, with the same shape as the schema dict.
   Attr types are `"str"`, `"int"`, `"bool"`, `"IntList"` or `"StrMap"`.
5. Caller mistakes raise `TypeError` or `RangeError`, corresponding to Python's `TypeError` or `ValueError`.
   The boolean options `partial`, `keepSource`, `html`, `cjkFriendly` and `canonical` require a real boolean; Python also accepts `0`, `1` and `None`.
6. JavaScript cannot represent every integer beyond ±2^53 exactly.
   JavaScript has one number type, so `1.0` reaches the core as the integer `1`; Python treats a float as another kind of value.
7. With strict checking off, coercing a non-string `type` or `text` uses each host's text conversion: Python `str()` or the JSON literal in JavaScript.
   Errors for wrongly typed scalars in a damaged stored form are also each host's own.

### JavaScript limits and measurements

- Inputs must be values JSON can carry.
  `undefined` object properties become absent keys; `NaN` and `Infinity` become `null` through `JSON.stringify`.
- JavaScript objects put integer-like keys first, so maps containing those keys can change entry order when passed through JavaScript.
- Wasm memory grows when needed and does not shrink; the largest document read determines its high-water mark.
- The shared nesting cap is 512, including the limit on simultaneously open declared mark tags.
  Stack margin at that cap was measured on Node only.
  In Firefox 160 documents at the cap converted and wrote canonical Markdown, on the main thread and in a worker;
  the margin there, and other browsers, were not measured.

Measurements recorded on 2026-11-15 used an Intel Core Ultra 9 185H on Linux x86_64, Node 26.13.0 and an Emscripten 6.0.13 Release build.
The wasm module was 611,095 bytes uncompressed.
The timings below include UTF-8 transfer, parsing, JSON output and `JSON.parse` for `fromMarkdown()` plus `toDict()`.
They exclude initialization, file reading and `free()`; each median is from three readings in one fresh process without a separate warmup.
These measurements describe those inputs and that environment, rather than a performance guarantee.

| Input at measurement time | UTF-8 bytes | Median, ms |
| --- | ---: | ---: |
| `README.md` | 66,106 | 3.646344 |
| `scripts.benchmark.make_fixture(1200, 4)` | 5,986,244 | 90.030844 |

## Development

```bash
python -m pip install .[test]
python -m pytest
```

To build and test both bindings from a clean checkout, install Python's pytest and pybind11, CMake/Ninja, Emscripten 6.0.13, Node 26 and global TypeScript 6.0.3:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DMARKTIP_BUILD_PYTHON=ON -DMARKTIP_BUILD_WASM=OFF \
  -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
EM_CACHE="$PWD/build-wasm/cache" emcmake cmake -S . -B build-wasm -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DMARKTIP_BUILD_PYTHON=OFF -DMARKTIP_BUILD_WASM=ON
cmake --build build
EM_CACHE="$PWD/build-wasm/cache" cmake --build build-wasm -j 4
python js/build.py
PYTHONPATH=python python scripts/generate_wasm_parity.py
PYTHONPATH=python python -m pytest -q
node --test js/test_document.ts js/test_schema.ts js/test_package.ts
tsc --project js/tsconfig.typecheck.json
PYTHONPATH=python python scripts/benchmark.py
```

The Node tests import `js/dist/`, so build the package and generate the parity fixture before running them.
