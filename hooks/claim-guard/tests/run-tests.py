#!/usr/bin/env python3
"""Regression tests for the Windows claim evidence guard."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
        self.assertTrue(resolved.samefile(self.root))


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


TRACKER = REPO / "hooks" / "claim-guard" / "windows" / "claim_ledger_tracker.py"
CLAIM = "I re-ran the suite and all tests pass."
QUOTED_ONLY = "I added `tests pass` and \u300c\u9a57\u8b49\u901a\u904e\u300d to the trigger list."


class LedgerFlowMixin:
    """Tracker then guard, as the agent would call them, for one build.

    Subclasses say how to run the tracker and the guard and what a tool call
    looks like for their agent. The payloads carry the fields the real agents
    send (hook_event_name, session ids, tool_input), not just the ones read.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def env(self) -> dict:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["CLAIM_GUARD_LEDGER_DIR"] = str(self.home / "ledger")
        return env

    def call(self, command: list, payload: dict) -> str:
        proc = subprocess.run(
            command, input=json.dumps(payload).encode("utf-8"), env=self.env(),
            capture_output=True, check=True, cwd=str(self.home),
        )
        return proc.stdout.decode("utf-8")

    def track(self, payload: dict) -> None:
        self.call(self.tracker_command, payload)
        time.sleep(0.05)  # file mtimes order the events; keep them apart

    def stop(self, message: str, stop_active: bool = False) -> str:
        return self.call(self.guard_command, self.stop_payload(message, stop_active))

    def assertBlocked(self, output: str, text: str = "") -> None:
        self.assertIn("block", output)
        self.assertIn(text, output)

    def assertAllowed(self, output: str) -> None:
        self.assertNotIn("block", output)

    def test_an_edit_after_the_last_test_run_makes_the_claim_stale(self) -> None:
        self.track(self.shell("pytest -q"))
        self.track(self.edit("src/app.py"))
        self.assertBlocked(self.stop(CLAIM), "stale verification")

    def test_a_test_run_after_the_last_edit_backs_the_claim(self) -> None:
        self.track(self.edit("src/app.py"))
        self.track(self.shell("pytest -q"))
        self.assertAllowed(self.stop(CLAIM))

    def test_the_second_pass_lets_a_stale_claim_through(self) -> None:
        self.track(self.shell("pytest -q"))
        self.track(self.edit("README.md"))
        self.assertAllowed(self.stop(CLAIM, stop_active=True))

    def test_a_quoted_phrase_is_a_mention_not_a_claim(self) -> None:
        self.assertAllowed(self.stop(QUOTED_ONLY))
        self.assertBlocked(self.stop(CLAIM))  # the same phrase unquoted still needs evidence

    def test_a_browser_test_run_counts_as_verification(self) -> None:
        self.track(self.shell("npx playwright test"))
        self.assertAllowed(self.stop(CLAIM))

    def test_a_web_search_counts_as_a_search(self) -> None:
        self.track(self.web_search("harness guard changelog"))
        self.assertAllowed(self.stop("That option does not exist in the current release."))


class ClaudePythonLedgerFlow(LedgerFlowMixin, unittest.TestCase):
    tracker_command = [sys.executable, str(TRACKER)]
    guard_command = [sys.executable, str(HOOK)]

    def tool(self, name: str, tool_input: dict) -> dict:
        return {"session_id": "flow", "hook_event_name": "PostToolUse", "cwd": str(self.home),
                "tool_name": name, "tool_input": tool_input, "tool_response": {}}

    def shell(self, command: str) -> dict:
        return self.tool("Bash", {"command": command})

    def edit(self, path: str) -> dict:
        return self.tool("Edit", {"file_path": path, "old_string": "a", "new_string": "b"})

    def web_search(self, query: str) -> dict:
        return self.tool("WebSearch", {"query": query})

    def stop_payload(self, message: str, stop_active: bool) -> dict:
        return {"session_id": "flow", "hook_event_name": "Stop", "cwd": str(self.home),
                "stop_hook_active": stop_active, "last_assistant_message": message}


class CodexPythonLedgerFlow(ClaudePythonLedgerFlow):
    tracker_command = [sys.executable, str(TRACKER), "--codex"]

    def tool(self, name: str, tool_input: dict) -> dict:
        payload = super().tool(name, tool_input)
        payload.update({"turn_id": "flow", "model": "gpt-5"})
        return payload

    def shell(self, command: str) -> dict:
        return self.tool("exec_command", {"command": command})

    def edit(self, path: str) -> dict:
        return self.tool("apply_patch", {"command": "*** Begin Patch\n*** Update File: %s" % path})


class AntigravityTrackerEditLedger(unittest.TestCase):
    """Antigravity's edit tools land in the edit ledger the Stop check reads."""

    def test_write_to_file_is_recorded_as_an_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["CLAIM_GUARD_LEDGER_DIR"] = tmp
            payload = {"conversationId": "agy-flow", "workspacePaths": [tmp],
                       "toolCall": {"name": "write_to_file",
                                    "args": {"TargetFile": tmp + "/a.py", "CodeContent": "x"}}}
            proc = subprocess.run([sys.executable, str(TRACKER)],
                                  input=json.dumps(payload).encode("utf-8"),
                                  env=env, capture_output=True, check=True)
            self.assertEqual(proc.stdout.decode().strip(), "{}")
            edit = Path(tmp) / "agy-flow.edit"
            self.assertIn("write_to_file", edit.read_text(encoding="utf-8"))
            self.assertFalse((Path(tmp) / "agy-flow.verify").exists())


@unittest.skipIf(os.name == "nt" or not shutil.which("jq"), "POSIX shell builds need bash and jq")
class ClaudeShellLedgerFlow(ClaudePythonLedgerFlow):
    tracker_command = ["bash", str(REPO / "hooks/claim-guard/claude-code/claim-ledger-tracker.sh")]
    guard_command = ["bash", str(REPO / "hooks/claim-guard/claude-code/claim-evidence-guard.sh")]


@unittest.skipIf(os.name == "nt" or not shutil.which("jq"), "POSIX shell builds need bash and jq")
class CodexShellLedgerFlow(ClaudePythonLedgerFlow):
    tracker_command = ["bash", str(REPO / "hooks/claim-guard/codex/claim-ledger-tracker.sh")]
    guard_command = ["bash", str(REPO / "hooks/claim-guard/codex/claim-evidence-guard.sh")]

    def tool(self, name: str, tool_input: dict) -> dict:
        payload = super().tool(name, tool_input)
        payload.update({"turn_id": "flow", "model": "gpt-5"})
        return payload

    def edit(self, path: str) -> dict:
        return self.tool("apply_patch", {"command": "*** Begin Patch\n*** Update File: %s" % path})

    def stop_payload(self, message: str, stop_active: bool) -> dict:
        payload = super().stop_payload(message, stop_active)
        payload["turn_id"] = "flow"
        return payload


if __name__ == "__main__":
    unittest.main()
