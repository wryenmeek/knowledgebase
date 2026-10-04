## 2025-09-26 - Python Performance Anti-Pattern: `.find('\n')` vs `.splitlines()`
**Learning:** Reverting a manual `while` loop that utilized `.find('\n')` for iterating over multiline strings back to the built-in `splitlines()` improves performance. Manual slicing loops run in Python bytecode and can be significantly slower than the C-optimized `splitlines()`.
**Action:** When extracting or iterating through a large document line by line, prefer `splitlines()` over custom string-slicing loops unless targeting early returns or small block extractions (where `.find('\n')` can bypass full string allocation).

## 2025-09-26 - Optimizing Line Tracking with `re.finditer`
**Learning:** When calculating line numbers for matches in large strings, using `splitlines()` with `enumerate()` allocates a large O(N) array. Using `re.finditer` and incrementally tracking lines via `content.count('\n', last_index, match.start())` avoids this allocation entirely and yields a substantial speedup.
**Action:** Replace `splitlines()` array allocations with `re.finditer` + incremental `content.count('\n')` when counting lines or locating pattern bounds in memory-sensitive paths.

## 2025-02-12 - Optimizing Stateful Parsing with `re.finditer`
**Learning:** When a parser uses `splitlines()` to do stateful parsing (like tracking if it is inside a frontmatter block or code fence), you can still optimize it by avoiding `splitlines()` entirely. By constructing a single `re.MULTILINE` regular expression that matches *all* relevant state-change markers (e.g. `^([ \t]*(?:---|```|~~~|\.\.\.).*|.*repo://.*)$`), you can use `re.finditer` to jump directly to the important lines. The current line number can be efficiently maintained using `text.count('\n', last_index, start_idx)`, yielding a ~4x speedup by keeping the iteration mostly in C.
**Action:** When optimizing stateful line-by-line parsers that use `splitlines()` and a loop, see if the state markers can be combined into a single regex and process them using `re.finditer` to avoid O(N) memory allocation and Python bytecode loop overhead for irrelevant lines.

## 2025-10-18 - Fast Early Returns with re.finditer
**Learning:** When checking if a large multi-line string contains at least one line matching a specific condition (e.g., using `any()` with `splitlines()`), `splitlines()` unconditionally allocates a massive O(N) list in memory. If the condition is met early, the allocation is completely wasted.
**Action:** Replace `splitlines()` loops in `any()` checks with `re.finditer(r"^(.*?)$", text, re.MULTILINE)` to lazily yield lines, allowing the loop to short-circuit and exit without full memory allocation, offering immense speedups on large files.
