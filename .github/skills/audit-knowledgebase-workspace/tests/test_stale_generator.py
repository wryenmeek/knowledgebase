"""Skill-local pytest entrypoint for deterministic stale-generator tests."""

from tests.kb.test_audit_workspace_stale_generator import AuditWorkspaceStaleGeneratorTests


__all__ = ["AuditWorkspaceStaleGeneratorTests"]
