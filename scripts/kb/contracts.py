"""Shared, spec-aligned contracts for knowledgebase tooling CLIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from typing import Any


class PolicyId(StrEnum):
    """Canonical policy identifiers from SPEC.md."""

    AUTO_PERSIST_WHEN_HIGH_VALUE = "auto_persist_when_high_value"
    CONTINUE_AND_REPORT_PER_SOURCE = "continue_and_report_per_source"
    LOG_ONLY_STATE_CHANGES = "log_only_state_changes"
    EXTERNAL_ASSETS_ALLOWED_AS_AUTHORITATIVE_IF_CHECKSUMED = (
        "external_assets_allowed_as_authoritative_if_checksumed"
    )
    CUSTOM_PER_WORKFLOW_MATRIX = "custom_per_workflow_matrix"
    WORKFLOW_CONCURRENCY_GROUP_PLUS_LOCAL_FILE_LOCK = (
        "workflow_concurrency_group_plus_local_file_lock"
    )


POLICY_IDENTIFIERS: tuple[str, ...] = tuple(policy.value for policy in PolicyId)


class TokenProfileId(StrEnum):
    """Canonical CI token profile identifiers from SPEC.md."""

    GATEKEEPER = "tp-gatekeeper"
    ANALYST_READONLY = "tp-analyst-readonly"
    PR_PRODUCER = "tp-pr-producer"


TOKEN_PROFILE_IDS: tuple[str, ...] = tuple(profile.value for profile in TokenProfileId)


WRITE_ALLOWLIST_PATHS: tuple[str, ...] = (
    "wiki/**",
    "wiki/index.md",
    "wiki/log.md",
    "raw/processed/**",
)
WRITE_LOCK_PATH = "wiki/.kb_write.lock"


class ResultStatus(StrEnum):
    """Machine-readable command status values."""

    WRITTEN = "written"
    NO_WRITE_POLICY = "no_write_policy"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ReasonCode(StrEnum):
    """Stable reason codes for policy and failure outcomes."""

    OK = "ok"
    POLICY_NOT_SATISFIED = "policy_not_satisfied"
    POLICY_CONFIDENCE_BELOW_MIN = "policy_confidence_below_min"
    POLICY_SOURCES_BELOW_MIN = "policy_sources_below_min"
    POLICY_UNRESOLVED_CONTRADICTION = "policy_unresolved_contradiction"
    LOCK_UNAVAILABLE = "lock_unavailable"
    PREREQ_MISSING_GHAW_READINESS = "prereq_missing:ghaw_readiness"
    PREREQ_MISSING_CONCURRENCY_GUARD = "prereq_missing:concurrency_guard"
    INVALID_INPUT = "invalid_input"
    PER_SOURCE_FAILURES = "per_source_failures"
    WRITE_FAILED = "write_failed"


REASON_CODES: tuple[str, ...] = tuple(reason.value for reason in ReasonCode)
RESULT_ENVELOPE_KEYS: tuple[str, ...] = (
    "status",
    "reason_code",
    "policy",
    "analysis_path",
    "index_updated",
    "log_appended",
    "sources",
)


@dataclass(frozen=True, slots=True)
class ResultEnvelope:
    """Centralized machine-readable result envelope."""

    status: ResultStatus | str
    reason_code: ReasonCode | str
    policy: tuple[PolicyId | str, ...] = field(default_factory=tuple)
    analysis_path: str | None = None
    index_updated: bool = False
    log_appended: bool = False
    sources: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "reason_code", str(self.reason_code))
        object.__setattr__(self, "policy", tuple(str(policy_id) for policy_id in self.policy))
        object.__setattr__(self, "sources", tuple(self.sources))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope into a JSON-compatible dictionary."""
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "policy": list(self.policy),
            "analysis_path": self.analysis_path,
            "index_updated": self.index_updated,
            "log_appended": self.log_appended,
            "sources": list(self.sources),
        }

    def to_json(self) -> str:
        """Serialize the envelope into deterministic JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)


__all__ = [
    "POLICY_IDENTIFIERS",
    "TOKEN_PROFILE_IDS",
    "WRITE_ALLOWLIST_PATHS",
    "WRITE_LOCK_PATH",
    "REASON_CODES",
    "RESULT_ENVELOPE_KEYS",
    "PolicyId",
    "TokenProfileId",
    "ResultStatus",
    "ReasonCode",
    "ResultEnvelope",
]
