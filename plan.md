1. **Optimize `extract_frontmatter_keys` in `scripts/kb/page_template_utils.py`**
   - The trace memory states: `Python Performance: Using splitlines() on multiline text unconditionally tokenizes the entire string into an O(N) memory array.`
   - I will replace the `splitlines()` loop in `extract_frontmatter_keys` with a `re.finditer` approach using `re.MULTILINE` to extract keys without allocating an intermediate list of lines.
   - I will also add a new compiled regex `_FRONTMATTER_KEY_MULTILINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", re.MULTILINE)` near the top of the file to support this.
   - Tool calls:
     ```json
     {
       "filepath": "scripts/kb/page_template_utils.py",
       "merge_diff": "<<<<<<< SEARCH\n_FRONTMATTER_KEY_RE = re.compile(r\"^([A-Za-z_][A-Za-z0-9_-]*)\\s*:\\s*(.*)$\")\n=======\n_FRONTMATTER_KEY_RE = re.compile(r\"^([A-Za-z_][A-Za-z0-9_-]*)\\s*:\\s*(.*)$\")\n_FRONTMATTER_KEY_MULTILINE_RE = re.compile(r\"^([A-Za-z_][A-Za-z0-9_-]*)\\s*:\", re.MULTILINE)\n>>>>>>> REPLACE"
     }
     ```
     ```json
     {
       "filepath": "scripts/kb/page_template_utils.py",
       "merge_diff": "<<<<<<< SEARCH\ndef extract_frontmatter_keys(frontmatter: str) -> set[str]:\n    \"\"\"Return the set of top-level key names present in a YAML frontmatter block.\"\"\"\n    keys: set[str] = set()\n    for line in frontmatter.splitlines():\n        match = _FRONTMATTER_KEY_RE.match(line)\n        if match:\n            keys.add(match.group(1))\n    return keys\n=======\ndef extract_frontmatter_keys(frontmatter: str) -> set[str]:\n    \"\"\"Return the set of top-level key names present in a YAML frontmatter block.\"\"\"\n    # ⚡ Bolt: Using re.finditer with re.MULTILINE avoids allocating an O(N) list from splitlines()\n    return {match.group(1) for match in _FRONTMATTER_KEY_MULTILINE_RE.finditer(frontmatter)}\n>>>>>>> REPLACE"
     }
     ```

2. **Verify changes and run tests**
   - Run formatting and linting: `ruff format scripts/kb/page_template_utils.py` and `ruff check scripts/kb/page_template_utils.py`.
   - Run the full test suite using `PYTHONPATH=.:/usr/lib/python3/dist-packages pytest tests/`.

3. **Complete pre-commit steps**
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.

4. **Submit the PR**
   - Branch name: `bolt-optimize-fm-keys`
   - Commit message: `⚡ Bolt: Optimize extract_frontmatter_keys memory allocation`
   - PR Title: `⚡ Bolt: Optimize extract_frontmatter_keys memory allocation`
   - PR Description: `💡 What: Replaced \`frontmatter.splitlines()\` with a multiline regex search (\`re.finditer\`) in \`extract_frontmatter_keys\`.\n🎯 Why: Using \`splitlines()\` unconditionally tokenizes the frontmatter block into an O(N) memory array. Using a regex search avoids this intermediate allocation and is significantly faster.\n📊 Impact: Reduced memory overhead and faster execution when parsing frontmatter keys.\n🔬 Measurement: Verify tests pass with the new implementation.`
