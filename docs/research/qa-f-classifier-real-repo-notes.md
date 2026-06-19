# QA-F classifier real-repo prep notes

- Gate-start commit SHA: `c0b96cd5fd5ffb11eab6ea4d40ba0663bcf164c9`
- Findings artifact: `/home/runner/work/knowledgebase/knowledgebase/docs/research/qa-f-classifier-real-repo-findings.json`
- Real-repo scope: `.github/copilot-instructions.md`, `AGENTS.md`

## Invocation used

```bash
cd /home/runner/work/knowledgebase/knowledgebase
python3 - <<'PY'
# importlib-loads skill_corpus_cache.py, stale_generator.py,
# redundancy_generator.py, friction_queries.py and writes:
# docs/research/qa-f-classifier-real-repo-findings.json
# (uses deterministic llm_caller fixture: {"claims": []}
# and OPEN stub for gh issue state probes)
PY
```

## Phase 7 cache_strategy verification

- `assembled_finding_count`: `0`
- `missing_cache_strategy_count`: `0`
- Result: every emitted finding (none emitted) satisfies cache-strategy field requirements.

## Cache adversarial fixtures (under tests/)

- Fixture A (touch SKILL.md, no content change, cache miss then same content):
  - `tests/kb/test_audit_workspace_cache.py::SkillCorpusCacheTests::test_touch_without_content_change_is_accepted_cache_miss_edge_case`
- Fixture B (modify body + preserve first paragraph + restore mtime via `os.utime`, stale cache hit accepted):
  - `tests/kb/test_audit_workspace_cache.py::SkillCorpusCacheTests::test_force_write_with_mtime_reset_hits_stale_cache_as_q11_false_negative`

## Mandatory-citation adversarial fixture

- Fixture (near-match non-existent skill path):
  - `tests/kb/test_audit_workspace_redundancy_generator.py::AuditWorkspaceRedundancyGeneratorTests::test_nonexistent_near_match_skill_citation_is_dropped_silently`
- Drop evidence:
  - Claims submitted: `1`
  - Findings emitted: `0`
  - Dropped finding count: `1`
  - Drop reason class: citation artifact path not present in the allowed lower-locality corpus map.

## Friction-query SQL audit notes

Reviewed `/home/runner/work/knowledgebase/knowledgebase/.github/skills/audit-knowledgebase-workspace/logic/friction_queries.py` templates.

- Injection hardening:
  - `repo` input is validated by `_REPO_PATTERN` and then quoted by `_repo_literal()`.
  - `days` is type-checked and range-bounded (`1..365`) before interval interpolation.
  - No caller-controlled freeform SQL fragments are accepted.
- Mandatory time-filter coverage:
  - Every template’s `primary` and `broader` SQL includes `> now() - INTERVAL '<N> days'` predicates.
  - Additional bounded windows exist for retry-loop matching (`RETRY_WINDOW_MINUTES`).

