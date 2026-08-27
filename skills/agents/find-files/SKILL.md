---
name: find-files
description: Find files on Windows from a topic or description using the Everything index, then inspect the strongest candidates to confirm intent. Use when the user wants to locate documents, spreadsheets, presentations, code, models, or other local files but does not know the exact filename.
allowed-tools:
  - mcp__everything-search__search
  - mcp__everything-search__search_detailed
  - mcp__everything-search__es_status
  - Read
  - Grep
  - Glob
---

# Find files by topic

Everything indexes names, paths, sizes, and dates, not file contents. Start with
a broad filename/path pass, then inspect likely candidates.

## Workflow

1. Call `es_status` once. If Everything or `es.exe` is unavailable, report
   that setup problem instead of treating it as zero results.
2. Expand the topic into 3-6 independent filename hypotheses: synonyms,
   abbreviations, project/product terms supplied by the user, and likely
   document types.
3. Run separate broad queries in parallel:
   - one concept or one OR-group per query;
   - `match_path=true`;
   - no extension filter initially;
   - a generous result limit;
   - newest-modified first.
4. Merge and deduplicate results. Prefer live, recent copies over obvious
   backups, caches, snapshots, shortcuts, or duplicate synced-library copies.
5. Add one narrowing constraint at a time only when needed: extension,
   `path_filter`, date window, or a second term.
6. Read or search the top candidates to confirm contents. Clearly distinguish a
   filename-only guess from a content-verified match.
7. Return a short ranked list with full paths, relevant dates/sizes when useful,
   and the reason for the ranking.

## Search guidance

- In Everything syntax, a space is AND. Avoid combining several guessed terms
  in the first pass.
- Use `<term one>|term2|term3` for alternatives.
- Use `!term` for exclusions after confirming the exclusion itself works.
- Prefer the structured `path_filter` parameter to an inline `path:` clause
  when directory names contain spaces.
- Add `ext:pdf;docx;pptx` or similar only after the broad pass.
- If a query returns nothing, widen it and try alternate names before
  concluding that no file exists.

## Safety

Searching and reading are non-interactive. Opening a file, revealing it in
Explorer, or launching an application operates the graphical interface. Do that
only after the user has explicitly approved the described UI-control action and
follow the host application's consent rules. Never use allowlist comments,
scratch-script conventions, or shell wrappers to bypass an approval boundary.
