"""Workflow contract checks for CI-5 GitHub monitor."""

from __future__ import annotations

import os
from pathlib import Path
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

    def _run_detect_script(
        self,
        *,
        event_name: str,
        dispatch_registry_path: str,
        workflow_registry_path: str = "",
        use_fake_python: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        script = self._detect_step_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            github_output_path = temp_root / "github-output.txt"
            github_output_path.write_text("", encoding="utf-8")

            env = os.environ.copy()
            env.update(
                {
                    "GITHUB_EVENT_NAME": event_name,
                    "DISPATCH_REGISTRY_PATH": dispatch_registry_path,
                    "REGISTRY_PATH": workflow_registry_path,
                    "GITHUB_OUTPUT": str(github_output_path),
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
            return result, github_output_path.read_text(encoding="utf-8")

    def _mask_steps(self) -> list[dict[str, object]]:
        steps: list[dict[str, object]] = []
        for job in self.workflow["jobs"].values():
            for step in job.get("steps", []):
                if step.get("name") == "Mask GitHub App token":
                    steps.append(step)
        return steps

    def test_repository_dispatch_registry_payload_validation_fails_closed(self) -> None:
        result, _ = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="../bad-path",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("Invalid repository_dispatch registry_path payload", combined_output)

    def test_repository_dispatch_registry_payload_validation_accepts_safe_hint(self) -> None:
        result, github_output = self._run_detect_script(
            event_name="repository_dispatch",
            dispatch_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("drift_detected=false", github_output)
        self.assertIn("artifact_name=drift-report-123456", github_output)

    def test_workflow_dispatch_registry_input_validation_fails_closed(self) -> None:
        result, _ = self._run_detect_script(
            event_name="workflow_dispatch",
            dispatch_registry_path="",
            workflow_registry_path="../bad-path",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("Invalid workflow_dispatch registry_path input", combined_output)

    def test_workflow_dispatch_registry_input_validation_accepts_safe_path(self) -> None:
        result, github_output = self._run_detect_script(
            event_name="workflow_dispatch",
            dispatch_registry_path="",
            workflow_registry_path="raw/github-sources/example.source-registry.json",
            use_fake_python=True,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("drift_detected=false", github_output)
        self.assertIn("artifact_name=drift-report-123456", github_output)

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
