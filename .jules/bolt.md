## 2025-09-26 - Python Performance Anti-Pattern: `.find('\n')` vs `.splitlines()`
**Learning:** Reverting a manual `while` loop that utilized `.find('\n')` for iterating over multiline strings back to the built-in `splitlines()` improves performance. Manual slicing loops run in Python bytecode and can be significantly slower than the C-optimized `splitlines()`.
**Action:** When extracting or iterating through a large document line by line, prefer `splitlines()` over custom string-slicing loops unless targeting early returns or small block extractions (where `.find('\n')` can bypass full string allocation).

## 2025-09-26 - Optimizing Line Tracking with `re.finditer`
**Learning:** When calculating line numbers for matches in large strings, using `splitlines()` with `enumerate()` allocates a large O(N) array. Using `re.finditer` and incrementally tracking lines via `content.count('\n', last_index, match.start())` avoids this allocation entirely and yields a substantial speedup.
**Action:** Replace `splitlines()` array allocations with `re.finditer` + incremental `content.count('\n')` when counting lines or locating pattern bounds in memory-sensitive paths.

## 2025-02-12 - Optimizing Stateful Parsing with `re.finditer`
**Learning:** When a parser uses `splitlines()` to do stateful parsing (like tracking if it is inside a frontmatter block or code fence), you can still optimize it by avoiding `splitlines()` entirely. By constructing a single `re.MULTILINE` regular expression that matches *all* relevant state-change markers (e.g. `^([ \t]*(?:---|```|~~~|\.\.\.).*|.*repo://.*)$`), you can use `re.finditer` to jump directly to the important lines. The current line number can be efficiently maintained using `text.count('\n', last_index, start_idx)`, yielding a ~4x speedup by keeping the iteration mostly in C.
**Action:** When optimizing stateful line-by-line parsers that use `splitlines()` and a loop, see if the state markers can be combined into a single regex and process them using `re.finditer` to avoid O(N) memory allocation and Python bytecode loop overhead for irrelevant lines.

## 2025-10-18 - Optimizing Markdown Table Parsing with finditer
**Learning:** When parsing rows from a Markdown table within a large document, using `splitlines()` and a loop introduces O(N) memory allocation and executes slow Python bytecode for every irrelevant line. Isolating the table block using `str.find()` and then applying `re.finditer` with `re.MULTILINE` (e.g., `^\|([^|\n]+)\|`) avoids list allocation and keeps the tight scanning loop in C, yielding a massive ~10x speedup for parsing `AGENTS.md`.
**Action:** When extracting or parsing Markdown tables from large files, avoid `splitlines()`. Instead, isolate the table block using string index bounds (`find()`) and parse the rows using a `MULTILINE` regex with `re.finditer()`.
