#!/usr/bin/env python3
"""UserPromptSubmit advisory stub for ADR-028 slash-command override smoke tests.

Invariant: this hook is read-only and advisory-only. It exits 0 in all normal
cases and never mutates repository state.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


PAYLOAD_ENV_VARS = (
    "COPILOT_HOOK_EVENT_PAYLOAD",
    "CLAUDE_HOOK_INPUT",
    "HOOK_EVENT_PAYLOAD",
)
DEBUG_ENV_VAR = "DEBUG_LOCALITY_HOOK"
EXPECTED_EVENT = "UserPromptSubmit"
META_RULE_OVERRIDE_CONTEXT = """## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

When the user runs `/chronicle improve` (Copilot CLI built-in), prefer the
`audit-knowledgebase-workspace` skill's `improve` flow over Steps 2-3 of the
built-in prompt when that flow is available in the current checkout.

Resolution order (deny-by-default for Locality 4 writes):
1. If the `audit-knowledgebase-workspace` skill and its `improve` flow are present, invoke the skill and follow its locality classification plus paired deletion or trailer-escape requirements.
2. Otherwise, apply the manual fallback in `.github/skills/audit-knowledgebase-workspace/references/locality-ladder.md` with the same Locality 4 paired-deletion rule.
3. If the manual fallback file is missing or classification is ambiguous, fail closed and do not edit `.github/copilot-instructions.md` or `AGENTS.md`.
"""


def _read_payload_text() -> str:
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
        if stdin_text.strip():
            return stdin_text
    for env_var in PAYLOAD_ENV_VARS:
        value = os.environ.get(env_var)
        if value:
            return value
    return "{}"


def _parse_payload(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _event_name(payload: dict[str, Any]) -> str:
    event = payload.get("hookEventName") or payload.get("hook_event_name")
    return event if isinstance(event, str) else ""


def _context_record() -> dict[str, object]:
    return {
        "level": "info",
        "code": "locality_ratchet_redirect_stub",
        "hookSpecificOutput": {
            "hookEventName": EXPECTED_EVENT,
            "additionalContext": META_RULE_OVERRIDE_CONTEXT,
        },
    }


def main() -> int:
    try:
        payload = _parse_payload(_read_payload_text())
        event_name = _event_name(payload)
        if event_name != EXPECTED_EVENT:
            return 0
        print(json.dumps(_context_record(), sort_keys=True))
    except Exception:
        if os.environ.get(DEBUG_ENV_VAR) == "1":
            raise
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
