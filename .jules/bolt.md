## 2025-09-26 - Python Performance Anti-Pattern: `.find('\n')` vs `.splitlines()`
**Learning:** Reverting a manual `while` loop that utilized `.find('\n')` for iterating over multiline strings back to the built-in `splitlines()` improves performance. Manual slicing loops run in Python bytecode and can be significantly slower than the C-optimized `splitlines()`.
**Action:** When extracting or iterating through a large document line by line, prefer `splitlines()` over custom string-slicing loops unless targeting early returns or small block extractions (where `.find('\n')` can bypass full string allocation).

## 2025-09-26 - Optimizing Line Tracking with `re.finditer`
**Learning:** When calculating line numbers for matches in large strings, using `splitlines()` with `enumerate()` allocates a large O(N) array. Using `re.finditer` and incrementally tracking lines via `content.count('\n', last_index, match.start())` avoids this allocation entirely and yields a substantial speedup.
**Action:** Replace `splitlines()` array allocations with `re.finditer` + incremental `content.count('\n')` when counting lines or locating pattern bounds in memory-sensitive paths.
