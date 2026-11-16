# MD4C vendored source

This directory vendors the parser-only MD4C 0.5.3 source files:

- `src/md4c.c`
- `src/md4c.h`
- `src/entity.c` (HTML entity table, used to decode `MD_TEXT_ENTITY`)
- `src/entity.h`
- `LICENSE.md`

Upstream: https://github.com/mity/md4c
Pinned tag: `release-0.5.3`

## Non-public API in use

`src/entities.cpp` calls `entity_lookup()` from `entity.h` directly,
to decode declared tag attrs and resolve references inside a link `href` / image `src` before the URI policy inspects them.
MD4C leaves `MD_TEXT_ENTITY` substrings verbatim in `MD_ATTRIBUTE`, so `&#106;avascript:` reaches the AST intact.
`src/parser.cpp` also calls `entity_lookup()` to decode `MD_TEXT_ENTITY` text into the document.
`entity.h` is an internal header — it is not covered by MD4C's API stability and carries no `extern "C"` guard.
An upstream bump therefore has to re-check that `const ENTITY* entity_lookup(const char*, size_t)` and the `&name;` key format still hold.

## Local patches (deviations from upstream)

- Top-level source segments (md4c.h, md4c.c): `MD_PARSER::source_segments` receives one ordered `MD_SOURCE_SEGMENT` array after pass 1 and before pass 2's root-child callbacks.
  Each segment starts at its opening physical line and is bound to the leaf or container record when created.
  Definitions-only top-level paragraphs retain a segment with `has_block = 0` when their record is removed.
  A null callback disables recording, and the callback array is valid only during the call.
  Patched hunks use `MARKTIP LOCAL PATCH` comments; the vendored version remains 0.5.3.
- Table header cell count (md4c.c): a table whose header row does not have as many cells as its delimiter row is emitted as a paragraph,
  as GFM specifies.
  Upstream keeps the table and drops the header cells beyond the delimiter row's count.
  The header is counted in pass 2 with the same cell boundaries `md_process_table_row()` uses,
  so an escaped pipe or a pipe inside a code span does not separate cells.
  Patched hunks use `MARKTIP LOCAL PATCH` comments.
- Task markers after blockquotes (md4c.c): the checkbox test uses the incoming item's container,
  rather than the innermost old container that may still be a blockquote.
  This preserves the next sibling's checked state and removes its checkbox from the text.
  The patch is marked `MARKTIP LOCAL PATCH`; this defect is also present on upstream master.
- Initial list-item blank lines (md4c.c): backported only this rule's handling from [upstream master f9e5eb232b95b737373ae706648cb75bd259ed1a](https://github.com/mity/md4c/blob/f9e5eb232b95b737373ae706648cb75bd259ed1a/src/md4c.c).
  The container records its LI opener's end and whether it has held content,
  and line analysis counts consecutive blank lines instead of reading the last block-buffer bytes as a header.
  This keeps a block following a fenced code block inside its list item.
  Patched hunks use `MARKTIP LOCAL PATCH` comments; the vendored version remains 0.5.3.
- Declared tags (md4c.h, md4c.c): `MD_PARSER::typed_tags` and `n_typed_tags` supply `MD_TYPED_TAG` entries in lexicographic name order.
  Names are NUL-terminated ASCII, and each entry carries a `block_line` boolean for block atoms and containers.
  Opening and closing names match case-sensitively.
  A declared tag at the start of a line skips every raw HTML block start condition,
  so Markdown inside the tag is parsed even when the tag occupies its own line.
  A complete `block_line` tag alone on a line with relative indentation below four spaces instead becomes a one-line HTML block,
  which interrupts paragraphs and ends before the newline without swallowing the following content.
  This uses the same tag grammar as inline HTML, including opening, closing and self-closing tags with attrs.
  The check precedes `MD_FLAG_NOHTMLBLOCKS`. Patched hunks use `MARKTIP LOCAL PATCH` comments.
- `MD_FLAG_CJKFRIENDLYEMPHASIS` (md4c.h, md4c.c, cjk.h): opt-in flag implementing the
  [CommonMark CJK-friendly Amendments Specification](https://github.com/tats-u/markdown-cjk-friendly/blob/main/specification.md)
  for emphasis (`*`, `_`) and strikethrough (`~`). CJK characters include East
  Asian Width `W`, `F`, or `H` except default emoji presentation, plus Hangul.
  Flanking distinguishes CJK punctuation and preceding variation-selector
  sequences, including standardized fullwidth quotation marks. Underscores
  retain CommonMark's additional intraword conditions, so `_《제목》_을` stays
  literal. `md_attention_flags()` shares flanking between emphasis and
  strikethrough. Patched hunks use `MARKTIP LOCAL PATCH` comments.
- Intra-word strikethrough (md4c.c, `~` branch in `md_collect_marks`):
  `~`/`~~` delimiter runs use the same graded flanking rules as `*` instead of
  upstream's strict require-whitespace/punctuation rule, matching cmark-gfm
  (which treats `~` like `*`): `a~~b~~c` strikes. The `$` (LaTeX math) branch
  keeps the original strict behavior, and the run-length cap (max 2) plus
  opener/closer length matching are unchanged. This is an always-on deviation
  from upstream md4c 0.5.3 (upstream rejects intra-word tildes; the GFM
  reference implementations accept them). Marked with a `MARKTIP LOCAL PATCH`
  comment.

## CJK classifier data

`src/cjk.h` is generated from Unicode 17.0.0 `EastAsianWidth.txt`, `Scripts.txt`,
`emoji/emoji-data.txt`, and `StandardizedVariants.txt`. Source URLs and SHA-256
digests are recorded in the header. The data license is `Unicode-LICENSE.txt`.
Ordinary whitespace and punctuation classification use MD4C's Unicode maps.

To regenerate, download the four files from
`https://www.unicode.org/Public/17.0.0/ucd/` into one directory (put
`emoji-data.txt` at its root), then run from the repository root:

```bash
python scripts/build_cjk_map.py /path/to/unicode-17.0.0
```
