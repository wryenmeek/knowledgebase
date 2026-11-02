1. **Optimize file paths parsing in `scripts/maintenance/audit_pr_body_vs_diff.py`**
   - In `_load_pr_from_gh`, when parsing the diff files output, replace the comprehension using `splitlines()` and `strip()` with natively invoking `.split()`.
   - `.split()` without arguments ignores all arbitrary whitespace and avoids evaluating Python bytecode, running natively in C and allocating less memory, giving roughly a ~2x speedup on whitespace-agnostic lines comparison operations.
2. **Pre-commit step**
   - Execute all testing commands (e.g. `pytest tests/`) to verify functionality.
   - Use `run_in_bash_session` to append a learning entry.
   - Run `pre_commit_instructions` and follow its instructions to ensure proper testing, verification, review, and reflection are done.
3. **Submit**
   - Submit the PR with a "⚡ Bolt" title and impact description.
