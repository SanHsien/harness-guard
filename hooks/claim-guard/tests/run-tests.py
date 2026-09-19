#!/usr/bin/env python3
"""Regression tests for the Windows claim evidence guard."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / "hooks" / "claim-guard" / "windows" / "claim_evidence_guard.py"
SPEC = importlib.util.spec_from_file_location("claim_evidence_guard", HOOK)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


class QualitySummaryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "tracked.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Harness Guard Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            cwd=self.root,
            check=True,
        )
        self.head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_policy(self) -> None:
        (self.root / "loop-policy.toml").write_text(
            "[verification]\nrequire_machine_evidence = true\n", encoding="utf-8"
        )

    def write_summary(self, **overrides: object) -> None:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile": "full",
            "passed": True,
            "commit": self.head,
            "gates": {"tests": True, "verify": True},
        }
        payload.update(overrides)
        artifacts = self.root / "artifacts"
        artifacts.mkdir(exist_ok=True)
        (artifacts / "quality-summary.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_repository_without_opt_in_is_ignored(self) -> None:
        self.assertIsNone(GUARD.check_quality_summary_gate(self.root))

    def test_missing_summary_fails_closed(self) -> None:
        self.write_policy()
        self.assertIn("does not exist", GUARD.check_quality_summary_gate(self.root))

    def test_valid_full_summary_for_head_is_allowed(self) -> None:
        self.write_policy()
        self.write_summary()
        self.assertIsNone(GUARD.check_quality_summary_gate(self.root))

    def test_missing_commit_is_rejected(self) -> None:
        self.write_policy()
        self.write_summary(commit=None)
        self.assertIn("commit", GUARD.check_quality_summary_gate(self.root))

    def test_non_object_summary_is_rejected(self) -> None:
        self.write_policy()
        artifacts = self.root / "artifacts"
        artifacts.mkdir(exist_ok=True)
        (artifacts / "quality-summary.json").write_text("[]", encoding="utf-8")
        self.assertIn("object", GUARD.check_quality_summary_gate(self.root))

    def test_quick_profile_is_rejected(self) -> None:
        self.write_policy()
        self.write_summary(profile="quick")
        self.assertIn("profile", GUARD.check_quality_summary_gate(self.root))

    def test_mismatched_head_is_rejected(self) -> None:
        self.write_policy()
        self.write_summary(commit="a" * 40)
        self.assertIn("does not match", GUARD.check_quality_summary_gate(self.root))

    def test_false_or_non_boolean_gate_is_rejected(self) -> None:
        self.write_policy()
        self.write_summary(gates={"tests": True, "verify": "yes"})
        self.assertIn("boolean", GUARD.check_quality_summary_gate(self.root))

        self.write_summary(passed=False, gates=[])
        self.assertIn("non-empty object", GUARD.check_quality_summary_gate(self.root))

    def test_nested_artifacts_directory_cannot_hide_repository_policy(self) -> None:
        self.write_policy()
        nested = self.root / "nested"
        (nested / "artifacts").mkdir(parents=True)
        resolved = GUARD.target_repo_root({"cwd": str(nested)})
        self.assertEqual(resolved, self.root)


@unittest.skipIf(os.name == "nt", "POSIX shell guard integration runs on Linux CI")
class PosixQualitySummaryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.home = Path(self.temp.name) / "home"
        self.root.mkdir()
        self.home.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "tracked.txt").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Harness Guard Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            cwd=self.root,
            check=True,
        )
        self.head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        (self.root / "loop-policy.toml").write_text(
            "[verification]\nrequire_machine_evidence = true\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_guard(self, relative_script: str, *, stop_active: bool = False) -> str:
        script = REPO / relative_script
        is_codex = "codex" in script.parts
        ledger_name = "codex-guard-hooks" if is_codex else "claude-guard-hooks"
        ledger = self.home / ".cache" / ledger_name / "guard-test.verify"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("pytest\n", encoding="utf-8")
        payload = {
            "session_id": "guard-test",
            "turn_id": "guard-test",
            "cwd": str(self.root),
            "last_assistant_message": "all tests pass",
            "stop_hook_active": stop_active,
        }
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        proc = subprocess.run(
            ["bash", str(script)],
            input=json.dumps(payload),
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        return proc.stdout

    def write_summary(self) -> None:
        artifacts = self.root / "artifacts"
        artifacts.mkdir(exist_ok=True)
        (artifacts / "quality-summary.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": "full",
                    "passed": True,
                    "commit": self.head,
                    "gates": {"tests": True},
                }
            ),
            encoding="utf-8",
        )

    def test_both_posix_guards_require_current_machine_evidence(self) -> None:
        scripts = (
            "hooks/claim-guard/claude-code/claim-evidence-guard.sh",
            "hooks/claim-guard/codex/claim-evidence-guard.sh",
        )
        for script in scripts:
            with self.subTest(script=script):
                summary = self.root / "artifacts" / "quality-summary.json"
                summary.unlink(missing_ok=True)
                output = self.run_guard(script, stop_active=True)
                self.assertIn("quality-summary.json", output)
                self.assertIn('"decision": "block"', output)

                self.write_summary()
                output = self.run_guard(script)
                self.assertNotIn('"decision": "block"', output)


if __name__ == "__main__":
    unittest.main()
