# MD4C vendored source

This directory vendors the parser-only MD4C 0.5.3 source files:

- `src/md4c.c`
- `src/md4c.h`
- `src/entity.c` (HTML entity table, used to decode `MD_TEXT_ENTITY`)
- `src/entity.h`
- `LICENSE.md`

Upstream: https://github.com/mity/md4c
Pinned tag: `release-0.5.3`

## Local patches (deviations from upstream)

- `MD_FLAG_CJKFRIENDLYEMPHASIS` (md4c.h, md4c.c): opt-in flag that relaxes the
  emphasis (`*`, `_`) and strikethrough (`~`) flanking rules so that a CJK
  character next to a delimiter does not prevent it from opening/closing
  (cf. markdown-it-cjk-friendly). Adds `md_is_cjk_char__()` and the
  `ISCJK`/`ISCJKBEFORE` macros. All patched hunks are marked with
  `MARKTIP LOCAL PATCH` comments. Behavior is unchanged unless the flag is set.
