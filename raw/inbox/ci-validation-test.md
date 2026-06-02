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
