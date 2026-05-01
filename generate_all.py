import json
import re
import pprint

# I need to analyze all the rest of the issues now.
# 19: Performance instrumentation and runtime budgets
# 18: Optimize lint_wiki and update_index
# 17: Skip persist_query index rebuild
# 16: Eliminate duplicate workflow YAML parsing in CI-2
# 15: Replace CI-3 source list GITHUB_OUTPUT handoff
# 14: Batch CI-3 ingest
# 13: Regression tests for symlink-safe writes
# 12: Harden .gitignore for secret-adjacent artifacts
# 11: Enforce authoritative approval controls for CI-3 manual dispatch
# 9: Remove CI-3 lock-file deletion step
# 8: Deprecate/remove no-op --result-json flag in persist_query
# 7: Make persist_query contradiction flag truly configurable
# 6: Close verification-matrix test gaps
# 5: Resolve spec/docs drift for entity/concept generation in ingest
# 4: Replace synthetic SourceRef SHA with real revision provenance
# 3: Enforce local write lock in update_index --write path
# 2: Harden write paths against symlink traversal
