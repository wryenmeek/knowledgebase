## 2026-11-04 - Optimizing Redundant Call Overhead in Comprehensions
**Learning:** Performing multiple identical method calls (like `.strip()`) on strings inside generator expressions and comprehensions results in redundant O(1) object allocations and measurable function call overhead on hot paths.
**Action:** Use the walrus operator (`:=`) in the conditional part of the comprehension or generator (e.g. `[stripped for item in items if (stripped := item.strip())]`) to evaluate the method once and reuse its outcome, preventing duplicate function calls and string allocations.

## 2026-11-04 - Optimizing the Line Content Extraction Hot Path
**Learning:** A fast-path loop to find newline characters using `str.find('\n')` is an anti-pattern due to significant Python bytecode execution overhead. Eagerly iterating over every line with `splitlines()` causes an `O(N)` list allocation that slows down early exits. A targeted `MULTILINE` regular expression paired with `re.finditer` parses lines more rapidly entirely in C.
**Action:** Use `re.finditer` with a `MULTILINE` regex matching non-empty lines (e.g. `^[ \t]*[^\s\n].*`) rather than looping over `splitlines()` to avoid memory allocation overhead and bytecode overhead when checking if a document contains command-like strings.
