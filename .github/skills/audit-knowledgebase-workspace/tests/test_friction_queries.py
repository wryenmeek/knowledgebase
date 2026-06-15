"""Skill-local entrypoint for the canonical friction-query test suite."""

from tests.kb.test_audit_workspace_friction_queries import (
    AuditWorkspaceFrictionQueryTests as TestAuditWorkspaceFrictionQueryTests,
)


__all__ = ["TestAuditWorkspaceFrictionQueryTests"]
