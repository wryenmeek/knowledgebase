"""Unit tests for github_customizations_freshness.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.kb.github_customizations_freshness import _suggest_replacement, run


class SuggestReplacementTests(unittest.TestCase):

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_suggest_replacement("", ["foo", "bar"]))

    def test_substring_match_forward(self) -> None:
        result = _suggest_replacement("validate-wiki", ["validate-wiki-governance"])
        self.assertEqual(result, "validate-wiki-governance")

    def test_substring_match_reverse(self) -> None:
        result = _suggest_replacement("validate-wiki-governance", ["validate-wiki"])
        self.assertEqual(result, "validate-wiki")

    def test_no_match_returns_none(self) -> None:
        result = _suggest_replacement("xyz-completely-different", ["foo", "bar", "baz"])
        self.assertIsNone(result)

    def test_difflib_fallback(self) -> None:
        result = _suggest_replacement("incremental-implementaton", ["incremental-implementation"])
        self.assertEqual(result, "incremental-implementation")

    def test_empty_candidates_returns_none(self) -> None:
        self.assertIsNone(_suggest_replacement("something", []))


class RunExitCodeTests(unittest.TestCase):

    def _make_empty_collectors(self):
        return (
            lambda: ([], []),
            lambda: ([], []),
            lambda: ([], []),
            lambda: ([], []),
        )

    def test_clean_repo_exits_0(self) -> None:
        with (
            patch("scripts.kb.github_customizations_freshness._collect_agent_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_copilot_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_hooks_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_prompt_drift", return_value=([], [])),
        ):
            code = run(output_path=None)
        self.assertEqual(code, 0)

    def test_drift_detected_exits_1(self) -> None:
        drift_entry = {"file": "f.md", "ref_broken": "old-skill", "ref_suggested": "new-skill"}
        with (
            patch("scripts.kb.github_customizations_freshness._collect_agent_drift", return_value=([drift_entry], [])),
            patch("scripts.kb.github_customizations_freshness._collect_copilot_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_hooks_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_prompt_drift", return_value=([], [])),
        ):
            code = run(output_path=None)
        self.assertEqual(code, 1)

    def test_write_error_exits_2(self) -> None:
        with (
            patch("scripts.kb.github_customizations_freshness._collect_agent_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_copilot_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_hooks_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_prompt_drift", return_value=([], [])),
        ):
            bad_path = Path("/no/such/directory/drift.json")
            code = run(output_path=bad_path)
        self.assertEqual(code, 2)

    def test_governed_path_output_exits_2(self) -> None:
        """--output inside wiki/ must be rejected without writing (Finding #24)."""
        wiki_path = REPO_ROOT / "wiki" / "drift-report.json"
        with (
            patch("scripts.kb.github_customizations_freshness._collect_agent_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_copilot_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_hooks_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_prompt_drift", return_value=([], [])),
        ):
            code = run(output_path=wiki_path)
        self.assertEqual(code, 2)
        self.assertFalse(wiki_path.exists())

    def test_output_file_written(self) -> None:
        drift_entry = {"file": "f.md", "ref_broken": "old", "ref_suggested": "new"}
        with (
            patch("scripts.kb.github_customizations_freshness._collect_agent_drift", return_value=([drift_entry], [])),
            patch("scripts.kb.github_customizations_freshness._collect_copilot_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_hooks_drift", return_value=([], [])),
            patch("scripts.kb.github_customizations_freshness._collect_prompt_drift", return_value=([], [])),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "drift.json"
                code = run(output_path=out)
                self.assertEqual(code, 1)
                report = json.loads(out.read_text())
        self.assertEqual(len(report["resolvable"]), 1)
        self.assertEqual(report["resolvable"][0]["ref_broken"], "old")


if __name__ == "__main__":
    unittest.main()
