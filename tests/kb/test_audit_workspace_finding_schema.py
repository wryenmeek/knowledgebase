"""Tests for the audit-workspace 10-bin classifier finding schema."""

from __future__ import annotations

import json
import re
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "schema"
    / "finding.schema.json"
)


class SchemaValidationError(AssertionError):
    """Raised by the stdlib-only schema validator used in this test module."""


class AuditWorkspaceFindingSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_all_10_destination_bins_validate(self) -> None:
        for finding in self._destination_examples():
            with self.subTest(destination=finding["destination"]):
                self.assert_schema_valid(finding)

    def test_two_examples_per_compliance_risk_value_validate(self) -> None:
        examples = {
            "deterministic": [
                self._finding(destination="Locality 0", compliance_risk="deterministic"),
                self._finding(destination="Locality 3d", compliance_risk="deterministic"),
            ],
            "agent-dependent": [
                self._finding(destination="Locality 1", compliance_risk="agent-dependent"),
                self._finding(destination="Locality 4", compliance_risk="agent-dependent"),
            ],
        }

        for compliance_risk, findings in examples.items():
            with self.subTest(compliance_risk=compliance_risk):
                self.assertEqual(len(findings), 2)
                for finding in findings:
                    self.assert_schema_valid(finding)

    def test_schema_rejects_missing_required_field(self) -> None:
        finding = self._finding()
        finding.pop("suggested_artifact_path")

        with self.assertRaisesRegex(SchemaValidationError, "missing required property"):
            self._validate_with_schema(finding, self.schema)

    def test_schema_rejects_invalid_destination(self) -> None:
        finding = self._finding(destination="OutOfBand")

        with self.assertRaisesRegex(SchemaValidationError, "destination"):
            self._validate_with_schema(finding, self.schema)

    def test_schema_rejects_invalid_compliance_risk(self) -> None:
        finding = self._finding(compliance_risk="maybe-deterministic")

        with self.assertRaisesRegex(SchemaValidationError, "compliance_risk"):
            self._validate_with_schema(finding, self.schema)

    def test_schema_rejects_non_numeric_expected_token_efficiency_rank(self) -> None:
        invalid_ranks = ("3", 3.5, True)

        for invalid_rank in invalid_ranks:
            with self.subTest(invalid_rank=invalid_rank):
                finding = self._finding(expected_token_efficiency_rank=invalid_rank)
                with self.assertRaisesRegex(SchemaValidationError, "expected_token_efficiency_rank"):
                    self._validate_with_schema(finding, self.schema)

    def test_schema_rejects_empty_cache_strategy(self) -> None:
        finding = self._finding(cache_strategy="")

        with self.assertRaisesRegex(SchemaValidationError, "cache_strategy"):
            self._validate_with_schema(finding, self.schema)

    def test_schema_rejects_unsafe_repo_relative_paths(self) -> None:
        unsafe_cases = (
            ("source_file", "/etc/passwd"),
            ("source_file", "file:///AGENTS.md"),
            ("suggested_artifact_path", "../../outside"),
            ("suggested_artifact_path", "docs//double-slash.md"),
            ("suggested_artifact_path", "docs/run;rm.md"),
            ("suggested_artifact_path", "docs/has space.md"),
            ("source_file", "docs/good.md\n"),
            ("suggested_artifact_path", "docs/good.md\n"),
            ("suggested_artifact_path", "docs/good.md\t"),
            ("suggested_artifact_path", r"docs\good.md"),
            ("suggested_artifact_path", "docs/foo:bar.md"),
            ("suggested_artifact_path", "docs/foo*.md"),
            ("suggested_artifact_path", "docs/"),
            ("suggested_artifact_path", "docs/./file.md"),
        )

        for field_name, unsafe_path in unsafe_cases:
            with self.subTest(field_name=field_name, unsafe_path=unsafe_path):
                finding = self._finding(**{field_name: unsafe_path})
                with self.assertRaisesRegex(SchemaValidationError, field_name):
                    self._validate_with_schema(finding, self.schema)

    def assert_schema_valid(self, finding: dict[str, Any]) -> None:
        self._validate_with_schema(deepcopy(finding), self.schema)

    @staticmethod
    def _finding(**overrides: Any) -> dict[str, Any]:
        finding = {
            "source_file": "AGENTS.md",
            "source_section": "## Write-surface matrix",
            "destination": "Locality 3a",
            "rationale": (
                "Per ADR-028 hidden-ratchet invariant: matching hook guidance can be "
                "delivered at the tool boundary."
            ),
            "compliance_risk": "deterministic",
            "expected_token_efficiency_rank": 3,
            "cache_strategy": "mtime_first_para",
            "suggested_artifact_path": ".github/hooks/check_locality_ratchet.py",
        }
        finding.update(overrides)
        return finding

    @classmethod
    def _destination_examples(cls) -> tuple[dict[str, Any], ...]:
        return (
            cls._finding(
                destination="Delete",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=0,
                suggested_artifact_path="AGENTS.md",
            ),
            cls._finding(
                destination="Locality 0",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=1,
                suggested_artifact_path="scripts/hooks/check_instructions_applyto_present.py",
            ),
            cls._finding(
                destination="Locality 1",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=2,
                suggested_artifact_path=".github/instructions/scripts.instructions.md",
            ),
            cls._finding(
                destination="Locality 2",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=3,
                suggested_artifact_path=".github/skills/audit-knowledgebase-workspace/SKILL.md",
            ),
            cls._finding(
                destination="Locality 3a",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=4,
                suggested_artifact_path=".github/hooks/hooks.json",
            ),
            cls._finding(
                destination="Locality 3b",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=5,
                suggested_artifact_path=".github/hooks/check_locality_ratchet.py",
            ),
            cls._finding(
                destination="Locality 3c",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=6,
                suggested_artifact_path=".github/hooks/check_context_md_format.py",
            ),
            cls._finding(
                destination="Locality 3d",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=7,
                suggested_artifact_path=".pre-commit-config.yaml",
            ),
            cls._finding(
                destination="Locality 3e",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=8,
                suggested_artifact_path=".github/hooks/hooks.json",
            ),
            cls._finding(
                destination="Locality 4",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=9,
                suggested_artifact_path=".github/copilot-instructions.md",
            ),
        )

    @classmethod
    def _validate_with_schema(cls, instance: Any, schema: dict[str, Any], path: str = "$") -> None:
        expected_type = schema.get("type")
        if expected_type is not None:
            cls._assert_type(instance, expected_type, path)

        if "enum" in schema and instance not in schema["enum"]:
            raise SchemaValidationError(f"{path}: value {instance!r} not in enum")

        if isinstance(instance, dict):
            required = schema.get("required", [])
            for property_name in required:
                if property_name not in instance:
                    raise SchemaValidationError(f"{path}: missing required property {property_name!r}")

            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                extra = sorted(set(instance) - set(properties))
                if extra:
                    raise SchemaValidationError(f"{path}: unexpected properties {extra!r}")

            for property_name, property_schema in properties.items():
                if property_name in instance:
                    cls._validate_with_schema(
                        instance[property_name],
                        property_schema,
                        f"{path}.{property_name}",
                    )

        if isinstance(instance, str):
            min_length = schema.get("minLength")
            if min_length is not None and len(instance) < min_length:
                raise SchemaValidationError(f"{path}: string shorter than minLength {min_length}")
            pattern = schema.get("pattern")
            if pattern is not None and re.search(pattern, instance) is None:
                raise SchemaValidationError(f"{path}: string does not match pattern {pattern!r}")

    @staticmethod
    def _assert_type(instance: Any, expected_type: str | list[str], path: str) -> None:
        expected_types = [expected_type] if isinstance(expected_type, str) else expected_type
        for single_type in expected_types:
            if single_type == "object" and isinstance(instance, dict):
                return
            if single_type == "string" and isinstance(instance, str):
                return
            if single_type == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
                return
            if single_type == "number" and (
                isinstance(instance, (int, float)) and not isinstance(instance, bool)
            ):
                return
            if single_type == "null" and instance is None:
                return
        raise SchemaValidationError(f"{path}: expected type {expected_types!r}")


if __name__ == "__main__":
    unittest.main()
