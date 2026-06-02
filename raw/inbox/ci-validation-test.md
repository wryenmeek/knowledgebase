# CI Validation Test

**Status:** Infrastructure validation test commit

This file is used to trigger the full CI-1 gatekeeper → CI-3 synthesis pipeline end-to-end validation.

When this file is pushed to `raw/inbox/`, CI-1 should:
1. Accept it (inbox-only path, no mixed-scope violation)
2. Trigger CI-3 via `workflow_run` event

CI-3 should then:
1. Run preflight validation (topology-hygiene, etc.)
2. Run synthesis (if no pre-existing entities exist)
3. Create PR with synthesized content if successful

This validates that the separated-commit strategy and infrastructure validation trigger model work correctly.

## Second validation pass

This update triggers a second CI-1 → CI-3 run to test the .gitignore fix for CI-3 workspace paths.

## Third validation pass

This update triggers a third CI-1 → CI-3 run to test the workspace path
exclusion fix for .qmd/, ci3-synthesis/, and ci3-metrics/.

## Fourth validation pass

Final end-to-end test with all CI-3 fixes:
- Workspace paths (.qmd/, ci3-synthesis/) excluded from validation
- raw/inbox files treated as read-only inputs
- Baseline capture before synthesis

This should complete the full CI-1 → CI-3 → PR creation pipeline.

## Fifth validation pass

Tests malformed status entry fix and baseline file exclusion.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>

## Sixth validation pass

Inbox-only commit after control-plane fix landed on previous SHA.

