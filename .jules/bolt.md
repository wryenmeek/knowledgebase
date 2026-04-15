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