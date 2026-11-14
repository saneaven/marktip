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

`src/policy.cpp` calls `entity_lookup()` from `entity.h` directly,
to resolve entity references inside a link `href` / image `src` before the URI policy inspects them.
MD4C leaves `MD_TEXT_ENTITY` substrings verbatim in `MD_ATTRIBUTE`, so `&#106;avascript:` reaches the AST intact.
`src/parser.cpp` also calls `entity_lookup()` to decode `MD_TEXT_ENTITY` text into the document.
`entity.h` is an internal header — it is not covered by MD4C's API stability and carries no `extern "C"` guard.
An upstream bump therefore has to re-check that `const ENTITY* entity_lookup(const char*, size_t)` and the `&name;` key format still hold.

## Local patches (deviations from upstream)

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
