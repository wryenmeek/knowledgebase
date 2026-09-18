## 2024-06-25 - Avoid splitlines on large strings for line numbers
**Learning:** Using `splitlines()` on a large file string unconditionally allocates an O(N) list in memory. For finding line numbers of specific patterns, using `re.finditer` with `re.MULTILINE` and tracking the line number via `content.count('\n', last_newline_idx, start)` is approximately 5x faster and avoids the memory overhead.
**Action:** When asked to extract line numbers of patterns in large strings, use `re.finditer` and `content.count('\n')` instead of `splitlines()` combined with a `enumerate()` loop.

## 2024-06-25 - Slice before processing localized markdown sections
**Learning:** Iterating over `splitlines()` to locate and parse a localized section (like a single Markdown table) forces parsing of the entire file string into an O(N) array.
**Action:** When a known section is bounded by text markers (e.g., specific headings), use `str.find` to compute the bounds of the section, slice the string, and apply `.splitlines()` or looping only to that much smaller slice. This typically yields a ~2x speedup or more depending on document size.
