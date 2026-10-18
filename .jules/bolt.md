## 2025-09-26 - Python Performance Anti-Pattern: `.find('\n')` vs `.splitlines()`
**Learning:** Reverting a manual `while` loop that utilized `.find('\n')` for iterating over multiline strings back to the built-in `splitlines()` improves performance. Manual slicing loops run in Python bytecode and can be significantly slower than the C-optimized `splitlines()`.
**Action:** When extracting or iterating through a large document line by line, prefer `splitlines()` over custom string-slicing loops unless targeting early returns or small block extractions (where `.find('\n')` can bypass full string allocation).

## 2025-09-26 - Optimizing Line Tracking with `re.finditer`
**Learning:** When calculating line numbers for matches in large strings, using `splitlines()` with `enumerate()` allocates a large O(N) array. Using `re.finditer` and incrementally tracking lines via `content.count('\n', last_index, match.start())` avoids this allocation entirely and yields a substantial speedup.
**Action:** Replace `splitlines()` array allocations with `re.finditer` + incremental `content.count('\n')` when counting lines or locating pattern bounds in memory-sensitive paths.

## 2025-02-12 - Optimizing Stateful Parsing with `re.finditer`
**Learning:** When a parser uses `splitlines()` to do stateful parsing (like tracking if it is inside a frontmatter block or code fence), you can still optimize it by avoiding `splitlines()` entirely. By constructing a single `re.MULTILINE` regular expression that matches *all* relevant state-change markers (e.g. `^([ \t]*(?:---|```|~~~|\.\.\.).*|.*repo://.*)$`), you can use `re.finditer` to jump directly to the important lines. The current line number can be efficiently maintained using `text.count('\n', last_index, start_idx)`, yielding a ~4x speedup by keeping the iteration mostly in C.
**Action:** When optimizing stateful line-by-line parsers that use `splitlines()` and a loop, see if the state markers can be combined into a single regex and process them using `re.finditer` to avoid O(N) memory allocation and Python bytecode loop overhead for irrelevant lines.
## 2025-10-09 - Optimizing Markdown Table Extraction
**Learning:** When extracting data from a specific Markdown table within a very large document (e.g., AGENTS.md), using `splitlines()` over the whole file introduces substantial O(N) memory allocation and Python bytecode overhead.
**Action:** Isolate the table block using `str.find()` index boundaries and parse rows directly with `re.finditer` and a `MULTILINE` regex to provide a massive, measurable speedup.
## 2024-10-06 - Replacing string slicing loops with compiled regexes in Python
**Learning:** Manual string slicing loops (e.g., using `find('\n')` in a `while` loop to stream through multiline strings without allocating lists via `splitlines()`) incur significant Python bytecode execution overhead.
**Action:** Replace manual string-slicing loops with highly optimized, C-level regular expressions evaluated via `re.finditer` and `re.MULTILINE`. For stateful parsing (like tracking markdown fenced code blocks), combine the boundary markers and the target patterns into a single alternation regex (`|`) to evaluate everything in one fast pass. Ensure to account for original `strip()` behavior in the regex (e.g., using `^[ \t]*`).
## 2025-10-07 - Optimizing Targeted Block Extraction in Markdown
**Learning:** When parsing a specific section (e.g., a table) from a large markdown file, applying `.splitlines()` over the entire file creates significant O(N) memory allocation and Python bytecode overhead. However, attempting to parse rows completely using `re.finditer` over the block can result in complex boundary and edge-case logic that sacrifices readability and risks correctness (like handling indentation for Markdown tables).
**Action:** Isolate the target block first using `re.search` with `re.MULTILINE` to find precise start and end boundaries. Slice the block and then apply `.splitlines()` only on this much smaller subset. Compute the starting line offset rapidly using the C-optimized `content.count('\n', 0, start_idx)` function. This strikes the perfect balance: it eliminates the heavy memory allocation of parsing irrelevant lines, keeps the table-parsing loop readable, and achieves roughly a 4x measurable speedup on large files without regressions.
## 2026-10-08 - Optimizing YAML List Extraction
**Learning:** When extracting a specific multi-line block (like YAML lists) from large multiline strings, avoid using `splitlines()` on the entire document to prevent O(N) memory allocation. Additionally, trying to optimize this by using a manual python `while` loop with `str.find('\n')` is a Python performance anti-pattern that runs slowly due to bytecode overhead.
**Action:** Use `re.search(pattern, text, re.MULTILINE)` to capture the entire target block as a regex group, and then use the C-optimized `.splitlines()` strictly on that smaller matched block. This is significantly faster and cleaner than manually streaming with `.find('\n')`.
## 2026-10-11 - Optimizing `_extract_trailers` with `re.finditer`
**Learning:** Extracting data line-by-line via `text.splitlines()` and `re.match` in a loop allocates a massive O(N) lines array for large git commit messages or PR bodies, resulting in unnecessary memory overhead and Python bytecode execution overhead.
**Action:** Replace the `splitlines()` loop with a fast-path literal string check (e.g., `if ':' not in text:`) and a single C-optimized `re.MULTILINE` search using `re.finditer`. This significantly cuts down allocation and provides a highly-measurable speedup on large text inputs.
## 2026-10-12 - Optimizing Section Content Checks with a Single Regex Search
**Learning:** Replacing a Python iteration loop that maps over a list of strings generated from `splitlines()` and calls `re.sub` sequentially, with a single, highly-optimized `re.MULTILINE` search (e.g. `re.search(r"^[ \t]*(?:[-*][ \t]*\S|[^-*\s])", text, re.MULTILINE)`) avoids O(N) memory allocation and Python bytecode overhead.
**Action:** When determining if any line in a multiline string matches a specific state or formatting constraint, prefer consolidating the parsing logic into a single regex search rather than splitting the lines and inspecting them iteratively in Python.

## 2026-10-14 - Optimizing Section Extraction with `re.finditer`
**Learning:** Parsing markdown template sections line-by-line via `text.splitlines()` in a loop allocates a massive O(N) lines array and executes slow Python bytecode for every single line, even irrelevant ones.
**Action:** Replace the `splitlines()` loop with a fast-path literal string check and a C-optimized `re.MULTILINE` search using `re.finditer` to jump directly to section headers. Then, use `splitlines()` only on the smaller isolated blocks. This significantly cuts down allocation and Python loop overhead, providing a measurable speedup.
## 2025-10-15 - Optimizing Subsequent Line Searching with Regex
**Learning:** Replacing a manual string-slicing `while` loop that uses `.find('\n')` to locate the first non-empty line after a match with a single `re.search(..., re.MULTILINE)` provides roughly a 10x speedup in Python. The regex approach operates mostly in highly optimized C code, avoiding slow Python bytecode execution overhead.
**Action:** When searching for specific subsequent lines (like the first non-empty line after a heading), avoid manual `while` loops using `.find('\n')`. Instead, use a single `re.search()` call with `re.MULTILINE` to capture the target line, starting from the end index of the previous match.

## 2024-10-18 - [Optimize file loading]
**Learning:** Using `read_text().splitlines()` allocates the entire file into memory as a string and as a list of lines.
**Action:** When iterating over lines from a file, use lazy file reading `with file_path.open() as f: for line in f:` to avoid loading the entire file into memory.
