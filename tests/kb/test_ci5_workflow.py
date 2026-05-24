"""Workflow contract checks for CI-5 GitHub monitor."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest

import yaml


WORKFLOW_PATH = Path(".github/workflows/ci-5-github-monitor.yml")


class Ci5WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.workflow_text)

    def _detect_step_script(self) -> str:
        steps = self.workflow["jobs"]["check-drift"]["steps"]
        for step in steps:
            if step.get("name") == "Check drift across all registries":
                script = step.get("run")
                self.assertIsInstance(script, str)
                return script.replace("${{ github.run_id }}", "123456")
        self.fail("Unable to locate CI-5 detect step script")

    @staticmethod
    def _is_allowlisted_registry_path(path: str) -> bool:
        if not path:
            return False
        candidate = PurePosixPath(path)
        return (
            not candidate.is_absolute()
            and ".." not in candidate.parts
            and path.startswith("raw/github-sources/")
            and path.endswith(".source-registry.json")
        )

    def _run_detect_script(
        self,
        *,
        event_name: str,
        dispatch_registry_path: str,
        workflow_registry_path: str = "",
        use_fake_python: bool = False,
        create_allowlisted_registry_files: bool = True,
        dispatch_source_kind: str = "github",
        dispatch_delivery_id: str = "delivery-123",
        dispatch_upstream_repo: str = "upstream-owner/upstream-repo",
        github_actor: str = "github-actions[bot]",
        run_attempt: str = "1",
        trusted_dispatch_actors: str = "github-actions[bot],wryenmeek",
    ) -> tuple[subprocess.CompletedProcess[str], str, str, str]:
        script = self._detect_step_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            github_output_path = temp_root / "github-output.txt"
            github_output_path.write_text("", encoding="utf-8")
            check_drift_args_path = temp_root / "check-drift-args.txt"
            check_drift_args_path.write_text("", encoding="utf-8")

            if create_allowlisted_registry_files:
                for candidate_path in (dispatch_registry_path, workflow_registry_path):
                    if self._is_allowlisted_registry_path(candidate_path):
                        registry_path = temp_root / candidate_path
                        registry_path.parent.mkdir(parents=True, exist_ok=True)
                        registry_path.write_text(
                            '{"version": "1", "entries": []}\n',
                            encoding="utf-8",
                        )

            env = os.environ.copy()
            env.update(
                {
                    "GITHUB_EVENT_NAME": event_name,
                    "DISPATCH_REGISTRY_PATH": dispatch_registry_path,
                    "DISPATCH_SOURCE_KIND": dispatch_source_kind,
                    "DISPATCH_DELIVERY_ID": dispatch_delivery_id,
                    "DISPATCH_UPSTREAM_REPO": dispatch_upstream_repo,
                    "REGISTRY_PATH": workflow_registry_path,
                    "GITHUB_ACTOR": github_actor,
                    "GITHUB_RUN_ATTEMPT": run_attempt,
                    "CI5_TRUSTED_DISPATCH_ACTORS": trusted_dispatch_actors,
                    "GITHUB_OUTPUT": str(github_output_path),
                    "FAKE_CHECK_DRIFT_ARGS_FILE": str(check_drift_args_path),
                }
            )

            if use_fake_python:
                fake_bin = temp_root / "bin"
                fake_bin.mkdir(parents=True, exist_ok=True)
                fake_python = fake_bin / "python"
                fake_python.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "if [[ \"${1:-}\" == \"-m\" ]] && [[ \"${2:-}\" == \"scripts.github_monitor.check_drift\" ]]; then\n"
                    "  printf '%s\\n' \"$@\" > \"${FAKE_CHECK_DRIFT_ARGS_FILE}\"\n"
                    "  out=\"drift-report.json\"\n"
                    "  shift 2\n"
                    "  while [[ $# -gt 0 ]]; do\n"
                    "    case \"${1}\" in\n"
                    "      --output)\n"
                    "        out=\"${2}\"\n"
                    "        shift 2\n"
                    "        ;;\n"
                    "      *)\n"
                    "        shift\n"
                    "        ;;\n"
                    "    esac\n"
                    "  done\n"
                    "  printf '{\"has_drift\": false}\\n' > \"${out}\"\n"
                    "  exit 0\n"
                    "fi\n"
                    "exec python3 \"$@\"\n",
                    encoding="utf-8",
                )
                fake_python.chmod(0o755)
                env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

            result = subprocess.run(
                ["bash", "-c", script],
                cwd=temp_root,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            return (
                result,
                github_output_path.read_text(encoding="utf-8"),
                check_drift_args_path.read_text(encoding="utf-8"),
                (
                    (temp_root / "runtime-metrics/fallback-telemetry.json").read_text(
                        encoding="utf-8"
                    )
                    if (temp_root / "runtime-metrics/fallback-telemetry.json").exists()
                    else ""
                ),
            )

    def _mask_steps(self) -> list[dict[str, object]]:
        steps: list[dict[str, object]] = []
        for job in self.workflow["jobs"].values():
            for step in job.get("steps", []):
                if step.get("name") == "Mask GitHub App token":
                    steps.append(step)
        return steps

    def test_repository_dispatch_invalid_registry_hint_falls_back_to_full_scan(self) -> None:
        result, github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="../bad-path",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "CI-5 full-scan fallback reason=invalid_registry_hint source=repository_dispatch",
            combined_output,
        )
        self.assertNotIn("--registry", check_drift_args)
        self.assertIn("drift_detected=false", github_output)

    def test_repository_dispatch_registry_payload_validation_accepts_safe_hint(self) -> None:
        result, github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("CI-5 targeted mode source=repository_dispatch", combined_output)
        self.assertIn("--registry", check_drift_args)
        self.assertIn("raw/github-sources/example.source-registry.json", check_drift_args)
        self.assertIn("drift_detected=false", github_output)
        self.assertIn("artifact_name=drift-report-123456", github_output)

    def test_repository_dispatch_safe_pattern_missing_file_falls_back(self) -> None:
        result, github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
            create_allowlisted_registry_files=False,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "CI-5 full-scan fallback reason=invalid_registry_hint source=repository_dispatch",
            combined_output,
        )
        self.assertNotIn("--registry", check_drift_args)
        self.assertIn("drift_detected=false", github_output)

    def test_repository_dispatch_hint_takes_precedence_over_workflow_input(self) -> None:
        result, _github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/dispatch.source-registry.json",
            workflow_registry_path="raw/github-sources/workflow.source-registry.json",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("--registry", check_drift_args)
        self.assertIn("raw/github-sources/dispatch.source-registry.json", check_drift_args)
        self.assertNotIn("raw/github-sources/workflow.source-registry.json", check_drift_args)

    def test_repository_dispatch_missing_registry_hint_falls_back_to_full_scan(self) -> None:
        result, github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "CI-5 full-scan fallback reason=missing_registry_hint source=repository_dispatch",
            combined_output,
        )
        self.assertNotIn("--registry", check_drift_args)
        self.assertIn("drift_detected=false", github_output)

    def test_workflow_dispatch_invalid_registry_input_falls_back_to_full_scan(self) -> None:
        result, github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="workflow_dispatch",
            dispatch_registry_path="",
            workflow_registry_path="../bad-path",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "CI-5 full-scan fallback reason=invalid_registry_hint source=workflow_dispatch",
            combined_output,
        )
        self.assertNotIn("--registry", check_drift_args)
        self.assertIn("drift_detected=false", github_output)

    def test_workflow_dispatch_registry_input_validation_accepts_safe_path(self) -> None:
        result, github_output, check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="workflow_dispatch",
            dispatch_registry_path="",
            workflow_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("CI-5 targeted mode source=workflow_dispatch", combined_output)
        self.assertIn("--registry", check_drift_args)
        self.assertIn("raw/github-sources/example.source-registry.json", check_drift_args)
        self.assertIn("drift_detected=false", github_output)
        self.assertIn("artifact_name=drift-report-123456", github_output)

    def test_repository_dispatch_rejects_untrusted_actor(self) -> None:
        result, _github_output, _check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
            github_actor="untrusted-user",
            trusted_dispatch_actors="github-actions[bot],wryenmeek",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("repository_dispatch rejected: untrusted actor", combined_output)

    def test_repository_dispatch_rejects_invalid_payload_contract(self) -> None:
        result, _github_output, _check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
            dispatch_source_kind="",
            dispatch_delivery_id="",
            dispatch_upstream_repo="bad-repo-format",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "repository_dispatch rejected: missing/invalid payload contract fields",
            combined_output,
        )

    def test_repository_dispatch_repeated_invalid_hint_emits_warning(self) -> None:
        result, _github_output, _check_drift_args, _fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="../bad-path",
            use_fake_python=True,
            run_attempt="2",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("repeated invalid-hint fallback detected", combined_output)

    def test_repository_dispatch_fallback_telemetry_contract_for_invalid_hint(self) -> None:
        result, _github_output, _check_drift_args, fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="../bad-path",
            use_fake_python=True,
            run_attempt="3",
            dispatch_delivery_id="delivery-telemetry-1",
            github_actor="github-actions[bot]",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertNotEqual(fallback_telemetry, "")
        payload = json.loads(fallback_telemetry)
        self.assertTrue(payload["fallback_triggered"])
        self.assertEqual(payload["fallback_reason"], "invalid_registry_hint")
        self.assertEqual(payload["event_name"], "repository_dispatch")
        self.assertEqual(payload["registry_hint_source"], "repository_dispatch")
        self.assertEqual(payload["effective_registry_path"], "")
        self.assertEqual(payload["dispatch_source_kind"], "github")
        self.assertEqual(payload["dispatch_delivery_id"], "delivery-telemetry-1")
        self.assertEqual(payload["run_attempt"], 3)

    def test_repository_dispatch_targeted_mode_telemetry_has_no_fallback(self) -> None:
        result, _github_output, check_drift_args, fallback_telemetry = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
            dispatch_delivery_id="delivery-telemetry-2",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("--registry", check_drift_args)
        payload = json.loads(fallback_telemetry)
        self.assertFalse(payload["fallback_triggered"])
        self.assertEqual(payload["fallback_reason"], "")
        self.assertEqual(
            payload["effective_registry_path"],
            "raw/github-sources/example.source-registry.json",
        )

    def test_mask_step_uses_env_indirection_for_token(self) -> None:
        mask_steps = self._mask_steps()
        self.assertEqual(len(mask_steps), 2, "Expected one mask step in each CI-5 job.")

        for step in mask_steps:
            env = step.get("env")
            self.assertIsInstance(env, dict)
            self.assertEqual(env.get("APP_TOKEN"), "${{ steps.app-token.outputs.token }}")

            run_script = step.get("run")
            self.assertIsInstance(run_script, str)
            self.assertIn("${APP_TOKEN}", run_script)
            self.assertNotIn("${{ steps.app-token.outputs.token }}", run_script)

    def test_no_run_block_inlines_app_token_expression(self) -> None:
        inline_expression = "${{ steps.app-token.outputs.token }}"
        for job in self.workflow["jobs"].values():
            for step in job.get("steps", []):
                run_script = step.get("run")
                if isinstance(run_script, str):
                    self.assertNotIn(
                        inline_expression,
                        run_script,
                        "run blocks must use env indirection for app token values.",
                    )


if __name__ == "__main__":
    unittest.main()
