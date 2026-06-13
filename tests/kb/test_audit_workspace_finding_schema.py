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
        """AC #2 (issue #203): all 10 destination bins validate."""

        for finding in self._destination_examples():
            with self.subTest(proposed_destination=finding["proposed_destination"]):
                self.assert_schema_valid(finding)

    def test_two_examples_per_compliance_risk_value_validate(self) -> None:
        """AC #6 (issue #203): two examples per compliance_risk value validate."""

        examples = {
            "deterministic": [
                self._finding(proposed_destination="Locality 0", compliance_risk="deterministic"),
                self._finding(proposed_destination="Locality 3d", compliance_risk="deterministic"),
            ],
            "agent-dependent": [
                self._finding(proposed_destination="Locality 1", compliance_risk="agent-dependent"),
                self._finding(proposed_destination="Locality 4", compliance_risk="agent-dependent"),
            ],
        }

        for compliance_risk, findings in examples.items():
            with self.subTest(compliance_risk=compliance_risk):
                self.assertEqual(len(findings), 2)
                for finding in findings:
                    self.assert_schema_valid(finding)

    def test_required_fields_complete_coverage(self) -> None:
        """AC #1 (issue #203): every required finding field is enforced."""

        for required_field in self.schema["required"]:
            with self.subTest(required_field=required_field):
                finding = self._finding()
                finding.pop(required_field)
                self.assert_schema_rejects(finding, required_field, "missing required property")

    def test_schema_rejects_unknown_property(self) -> None:
        """AC #6 (issue #203): invalid findings reject unknown contract fields."""

        finding = self._finding(mystery_field="x")

        self.assert_schema_rejects(finding, "mystery_field", "unexpected properties")

    def test_optional_nullable_fields_accept_string_null_or_absent(self) -> None:
        """AC #6 (issue #203): optional citation fields accept string, null, or absent."""

        for field_name in ("deletion_candidate", "citation"):
            with self.subTest(field_name=field_name, value="absent"):
                self.assert_schema_valid(self._finding())
            with self.subTest(field_name=field_name, value=None):
                self.assert_schema_valid(self._finding(**{field_name: None}))
            with self.subTest(field_name=field_name, value="artifact path + snippet"):
                self.assert_schema_valid(self._finding(**{field_name: "artifact path + snippet"}))
            for invalid_value in (42, []):
                with self.subTest(field_name=field_name, invalid_value=invalid_value):
                    finding = self._finding(**{field_name: invalid_value})
                    self.assert_schema_rejects(finding, field_name, "expected type")

    def test_schema_rejects_invalid_destination(self) -> None:
        """AC #2 (issue #203): destination bins are closed to the 10 approved values."""

        finding = self._finding(proposed_destination="OutOfBand")

        self.assert_schema_rejects(finding, "proposed_destination", "not in enum")

    def test_schema_rejects_invalid_compliance_risk(self) -> None:
        """AC #3 (issue #203): compliance_risk is deterministic or agent-dependent."""

        finding = self._finding(compliance_risk="maybe-deterministic")

        self.assert_schema_rejects(finding, "compliance_risk", "not in enum")

    def test_schema_rejects_invalid_expected_token_efficiency_rank(self) -> None:
        """AC #4 (issue #203): expected_token_efficiency_rank is a non-negative integer."""

        invalid_cases = (
            ("3", "expected type"),
            (3.5, "expected type"),
            (True, "expected type"),
            (-1, "minimum"),
        )

        for invalid_rank, expected_message in invalid_cases:
            with self.subTest(invalid_rank=invalid_rank):
                finding = self._finding(expected_token_efficiency_rank=invalid_rank)
                self.assert_schema_rejects(
                    finding,
                    "expected_token_efficiency_rank",
                    expected_message,
                )

    def test_cache_strategy_enum_accepts_documented_values_and_rejects_typo(self) -> None:
        """AC #5 (issue #203): cache_strategy is the closed Phase 4/Q11 enum."""

        for valid_strategy in ("mtime_first_para", "hybrid_signature"):
            with self.subTest(valid_strategy=valid_strategy):
                self.assert_schema_valid(self._finding(cache_strategy=valid_strategy))

        for invalid_strategy in ("", "mtime_first_paragraph"):
            with self.subTest(invalid_strategy=invalid_strategy):
                finding = self._finding(cache_strategy=invalid_strategy)
                self.assert_schema_rejects(finding, "cache_strategy", "not in enum")

    def test_schema_rejects_min_length_string_fields_when_empty(self) -> None:
        """AC #1 (issue #203): required text fields reject empty strings."""

        for field_name in ("source_file", "source_section", "rationale", "suggested_artifact_path"):
            with self.subTest(field_name=field_name):
                finding = self._finding(**{field_name: ""})
                self.assert_schema_rejects(finding, field_name, "minLength")

    def test_schema_rejects_unsafe_repo_relative_paths(self) -> None:
        """AC #6 (issue #203): invalid path examples reject unsafe repo paths."""

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
                self.assert_schema_rejects(finding, field_name, "pattern")

    def assert_schema_valid(self, finding: dict[str, Any]) -> None:
        self._validate_with_schema(deepcopy(finding), self.schema)

    def assert_schema_rejects(
        self,
        finding: dict[str, Any],
        field_name: str,
        expected_message: str,
    ) -> None:
        with self.assertRaises(SchemaValidationError) as context:
            self._validate_with_schema(finding, self.schema)
        message = str(context.exception)
        self.assertIn(field_name, message)
        self.assertIn(expected_message, message)

    @staticmethod
    def _finding(**overrides: Any) -> dict[str, Any]:
        finding = {
            "source_file": "AGENTS.md",
            "source_section": "## Write-surface matrix",
            "proposed_destination": "Locality 3a",
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
                proposed_destination="Delete",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=0,
                suggested_artifact_path="AGENTS.md",
            ),
            cls._finding(
                proposed_destination="Locality 0",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=1,
                suggested_artifact_path="scripts/hooks/check_instructions_applyto_present.py",
            ),
            cls._finding(
                proposed_destination="Locality 1",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=2,
                suggested_artifact_path=".github/instructions/scripts.instructions.md",
            ),
            cls._finding(
                proposed_destination="Locality 2",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=3,
                suggested_artifact_path=".github/skills/audit-knowledgebase-workspace/SKILL.md",
            ),
            cls._finding(
                proposed_destination="Locality 3a",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=4,
                suggested_artifact_path=".github/hooks/hooks.json",
            ),
            cls._finding(
                proposed_destination="Locality 3b",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=5,
                suggested_artifact_path=".github/hooks/check_locality_ratchet.py",
            ),
            cls._finding(
                proposed_destination="Locality 3c",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=6,
                suggested_artifact_path=".github/hooks/check_context_md_format.py",
            ),
            cls._finding(
                proposed_destination="Locality 3d",
                compliance_risk="deterministic",
                expected_token_efficiency_rank=7,
                suggested_artifact_path=".pre-commit-config.yaml",
            ),
            cls._finding(
                proposed_destination="Locality 3e",
                compliance_risk="agent-dependent",
                expected_token_efficiency_rank=8,
                suggested_artifact_path=".github/hooks/hooks.json",
            ),
            cls._finding(
                proposed_destination="Locality 4",
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

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            minimum = schema.get("minimum")
            if minimum is not None and instance < minimum:
                raise SchemaValidationError(f"{path}: number below minimum {minimum}")

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
