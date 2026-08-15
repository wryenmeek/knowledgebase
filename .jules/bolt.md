## ⚡ Performance Optimization: scripts/kb/update_index.py

**💡 What:** Removed sequential array allocation and sort `sorted(rglob("*.md"))` during directory traversal and removed an unnecessary $O(N)$ total_files count using `rglob()`. Both functions were optimized to stream path generators directly into an unconditional `ProcessPoolExecutor.map` with `chunksize=100`.

**🎯 Why:** Sorting an array of a full deep filesystem tree `rglob` blocks execution of multiprocess mapping until the filesystem is fully traversed, loaded into memory, and sorted. We sort the list of values later, so sorting the initial path list is redundant. Furthermore, computing `total_files` sequentially to check `use_pool` requires an unnecessary second deep filesystem scan, meaning large repositories pay the `rglob` sequential penalty twice before processing even starts.

**📊 Measured Improvement:**
- Established baseline: ~0.22s
- Improved time: ~0.18s
- Impact: 18% execution time reduction and lower peak memory allocations because generators `rglob` are now streamed continuously in parallel chunks into `ProcessPoolExecutor` without materializing in memory just to be sorted. On larger wikis, the impact of avoiding `N log N` operations and an entire secondary `N` OS stat traversal scales highly.

## 🧪 test coverage for sourceref whitespace inputs

- Learned that `scripts/kb/sourceref.py` implements input validation.
- Enhanced boundary conditions tests by ensuring various types of whitespace are handled correctly by the parser in `validate_sourceref`.

## ⚡ Bolt Optimization: scripts/kb/lint_wiki.py

**💡 Learning:** Eager `pathlib.Path.resolve()` calls inside hot loops (like `Path.rglob()`) cause a severe performance bottleneck due to excessive and expensive OS stat calls. Additionally, using `try/except Path.relative_to()` for bounds checking is slower and less pythonic than `Path.is_relative_to()`.

**🎯 Action:** Remove eager `.resolve()` calls in hot loops when iterating over paths, resolving only when strictly necessary. Use `.is_relative_to()` for bounds checking instead of `try/except ValueError` with `.relative_to()`.

## ⚡ Bolt: scripts/kb/lint_wiki.py performance anti-pattern

**💡 Learning:** `Path.resolve()` is significantly slower than building and asserting paths, and `Path.is_relative_to()` is much faster than `Path.relative_to()`. When validating large amounts of files, defer resolving to absolute paths if not necessary.

**🎯 Action:** Replace `Path.relative_to(root)` in try/except blocks with `Path.is_relative_to(root)`. Avoid unnecessary `Path.resolve()` calls in hot paths like link target resolution in the wiki linter.
## 2026-04-15 - [Path bounds checking optimization]
**Learning:** Using `try/except Path.relative_to()` is slower than the natively implemented string comparison under the hood of `Path.is_relative_to()` for bounds checking. This is an anti-pattern that slows down path validation logic.
**Action:** Replace `try/except Path.relative_to()` with `Path.is_relative_to()` for performance gains across the python codebase.

## 2026-04-21 - [File chunk reading optimization]
**Learning:** When reading files in chunks (e.g., for hashing), using `iter(lambda: handle.read(size), b"")` introduces significant lambda closure overhead, which hurts efficiency in hot loops.
**Action:** Always prefer using a `while` loop with the walrus operator (`while chunk := handle.read(size):`) to eliminate lambda closure overhead and improve performance.
## 2026-06-19 - [Performance] Regex for markdown frontmatter extraction
**Learning:** Avoid using `str.splitlines()` on an entire large text file just to extract a small header (e.g., markdown frontmatter). This completely tokenizes the string into memory row-by-row, creating massive latency and memory overhead.
**Action:** Use a fast-path literal check (e.g., `text.lstrip(" \t").startswith("---")`) combined with a targeted regular expression (`_FRONTMATTER_BLOCK_RE.match(text)`) for targeted extraction.
## 2026-06-20 - [Test Boundary Adherence for Ratchets]
**Learning:** Repository-wide configuration contracts, metric baselines, and ratchets (e.g., `MAX_APPROVAL_FLAG_SCRIPTS`, `MAX_UNITTEST_FILES`) are centralized in `scripts/kb/contracts.py` and strictly validated by unit tests in `tests/kb/test_contracts.py`. Changes to ratchet values must be updated in both files.
**Action:** When updating a ratchet test file (e.g., changing from `<=` to `==`), also modify its contract testing baseline in `test_contracts.py` to match the exact current value to satisfy file boundaries safely.
## 2026-06-25 - [Performance] Optimized Python String Slicing vs splitlines()
**Learning:** Using `text.splitlines()` on large text strings creates a heavy memory footprint by tokenizing strings into `O(N)` arrays. For fast-path validation like extracting frontmatter delimiters or stripping metadata, isolating subsets of strings with `.find('\n')` achieves `O(1)` space allocation. Furthermore, calling `.lstrip()` or `.partition()` on large, untokenized strings will create full-sized string object copies under the hood.
**Action:** When validating single lines in a large text document, use `newline_pos = text.find('\n')` and slice `text[:newline_pos]` before applying fast-path methods like `.lstrip()` or `.startswith()`.
## 2026-06-25 - [Performance] Avoid intermediate set allocation in missing keys check
**Learning:** When computing the difference between a set and a dictionary's keys to check for missing required fields, `required - set(my_dict)` or `required - set(my_dict.keys())` creates an unnecessary `O(N)` set object in memory.
**Action:** Use dictionary view set operations or natively implemented set methods, such as `required.difference(my_dict)` or `required.difference(my_dict.keys())` to achieve better performance and eliminate redundant allocations.

## 2026-06-24 - [Performance] Removing O(N) splitlines() array allocation for multi-line extraction
**Learning:** Using `splitlines()` on multiline text blocks (e.g. Markdown bodies) unconditionally tokenizes the entire string into an $O(N)$ memory array, creating unnecessary allocations and garbage collection overhead. Extracting headings with a `while` loop over string slices delimited by `.find('\n')` entirely eliminates this memory spike (true $O(1)$) and processes substantially faster, especially when combining slicing with early-out heuristics before applying regex matching.
**Action:** Avoid `splitlines()` on document bodies. Use `.find('\n')` to stream through large strings safely with minimal allocation overhead.

## 2024-05-19 - Avoid Intermediate Set Creation for Dict Views
**Learning:** In Python 3, dictionary views (`dict.keys()`, `dict.items()`) behave identically to sets and fully support set operations (like `-`, `&`, `|`, `^`). Converting them explicitly to sets (`set(d.keys()) - other_set`) is an anti-pattern that creates an unnecessary, memory-allocating intermediate object. Similarly, `set1 - set(d.keys())` allocates a new set, whereas `set1.difference(d)` iterates over `d` directly and is faster.
**Action:** Always prefer native dictionary view operations (e.g., `d.keys() - other_set` or `set1.difference(d)`) to avoid intermediate O(N) memory allocations during set arithmetic.
## 2026-08-14 - [Performance] Avoiding splitlines()[0] on large text strings
**Learning:** Using `text.splitlines()[0]` to extract just the first line of a potentially large text document (like a PR body) tokenizes the entire string into an $O(N)$ memory array just to return the first element.
**Action:** Use `.find('
')` and string slicing (e.g., `text[:nl_pos]`) to extract the first line without allocating an array of all lines, achieving $O(1)$ memory allocation.## 2026-06-25 - [Performance] Fast-path literal check to avoid O(N) splitlines allocation
**Learning:** Using `splitlines()` on multiline text unconditionally tokenizes the entire string into an $O(N)$ memory array, creating unnecessary allocations and garbage collection overhead. For fast-path validation like searching for specific prefixes or substrings (e.g. `repo://` or `sources:`), adding an `if target not in text` early return completely bypasses this expensive operation when the target pattern is absent, yielding massive performance gains for large files.
**Action:** When extracting or validating string structures line-by-line where a specific literal substring is expected, always add a fast-path literal string check (`in` or `not in`) before calling `splitlines()`.
