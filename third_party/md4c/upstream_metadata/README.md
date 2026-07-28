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

`src/ast.cpp` calls `entity_lookup()` from `entity.h` directly,
to resolve entity references inside a link `href` / image `src` before the URI policy inspects them.
MD4C leaves `MD_TEXT_ENTITY` substrings verbatim in `MD_ATTRIBUTE`, so `&#106;avascript:` reaches the AST intact.
`entity.h` is an internal header — it is not covered by MD4C's API stability and carries no `extern "C"` guard.
An upstream bump therefore has to re-check that `const ENTITY* entity_lookup(const char*, size_t)` and the `&name;` key format still hold.

## Local patches (deviations from upstream)

- `MD_FLAG_CJKFRIENDLYEMPHASIS` (md4c.h, md4c.c): opt-in flag that relaxes the
  emphasis (`*`, `_`) and strikethrough (`~`) flanking rules so that a CJK
  character next to a delimiter does not prevent it from opening/closing
  (cf. markdown-it-cjk-friendly). Adds `md_is_cjk_char__()` and the
  `ISCJK`/`ISCJKBEFORE` macros. All patched hunks are marked with
  `MARKTIP LOCAL PATCH` comments. Behavior is unchanged unless the flag is set.
- Intra-word strikethrough (md4c.c, `~` branch in `md_collect_marks`):
  `~`/`~~` delimiter runs use the same graded flanking rules as `*` instead of
  upstream's strict require-whitespace/punctuation rule, matching cmark-gfm
  (which treats `~` like `*`): `a~~b~~c` strikes. The `$` (LaTeX math) branch
  keeps the original strict behavior, and the run-length cap (max 2) plus
  opener/closer length matching are unchanged. This is an always-on deviation
  from upstream md4c 0.5.3 (upstream rejects intra-word tildes; the GFM
  reference implementations accept them). Marked with a `MARKTIP LOCAL PATCH`
  comment.
