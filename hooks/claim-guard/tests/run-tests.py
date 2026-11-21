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
# A claim wrapped in quotes is still a claim (2026-11-09: the quote-stripping that let
# these through was reverted; see NOT_A_CLAIM in windows/claim_evidence_guard.py).
QUOTED_CLAIMS = (
    "Done. All `tests pass`.",
    "\u5b8c\u6210\uff0c\u300c\u9a57\u8b49\u901a\u904e\u300d\u3002",
    "Fixed it -- `verified` on the live box.",
    # Words glued to the trigger by punctuation or a prefix are still claims.
    "I reverified it.",
    "Built/verified.",
    "tests/verified OK",
    "Done.Verified",
    "verified(live box)",
    "Fixed, yet verified twice.",
    "The net verified count went up.",
    "Deployed.Verified.Go ahead.",
    "Done--verified on CI.",
    "Deployed and verified.go ahead and merge.",
    "Built and confirmed.md is ready.",
)
# Code that merely contains a trigger word, and negated claims: not claims.
NOT_CLAIMS = (
    "Renamed `is_verified` to `verified_at` and added `confirmed()`.",
    "The flag is `--confirmed`; the helper lives in `lib/verified.py`.",
    "Edited the parser; not yet verified.",
    "That path is still unconfirmed and was never verified.",
    "The fix isn't verified yet.",
)


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

    extra_env: dict = {}

    def env(self) -> dict:
        env = os.environ.copy()
        env.pop("CLAIM_GUARD_TEST_CMD", None)
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["CLAIM_GUARD_LEDGER_DIR"] = str(self.home / "ledger")
        env.update(self.extra_env)
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

    def test_a_quoted_claim_still_needs_evidence(self) -> None:
        for message in QUOTED_CLAIMS:
            with self.subTest(message=message):
                self.assertBlocked(self.stop(message))

    def test_code_identifiers_and_negations_are_not_claims(self) -> None:
        for message in NOT_CLAIMS:
            with self.subTest(message=message):
                self.assertAllowed(self.stop(message))

    def test_a_browser_test_run_counts_as_verification(self) -> None:
        self.track(self.shell("npx playwright test"))
        self.assertAllowed(self.stop(CLAIM))

    def test_a_web_search_counts_as_a_search(self) -> None:
        self.track(self.web_search("harness guard changelog"))
        self.assertAllowed(self.stop("That option does not exist in the current release."))

    # -- two tiers: a test claim wants a test or build run, not a status query --
    # Measured on 40 local sessions (2026-11-21) before choosing the strength: a
    # block would have been wrong about half the time, so this tier is a notice
    # the user sees, and never a block. The tier-one ledger rules are unchanged.

    def notice(self, output: str) -> str:
        """The systemMessage a Claude Code / Codex Stop hook shows the user, or ""."""
        output = output.strip()
        if not output:
            return ""
        return json.loads(output).get("systemMessage") or ""

    def assertNoticed(self, output: str, text: str) -> None:
        self.assertAllowed(output)
        self.assertIn(text, self.notice(output))

    def assertQuiet(self, output: str) -> None:
        self.assertAllowed(output)
        self.assertEqual(self.notice(output), "")

    def test_a_status_query_alone_does_not_back_a_test_claim(self) -> None:
        self.track(self.shell("git status"))
        self.assertNoticed(self.stop(CLAIM), "no test or build command")

    def test_a_status_query_alone_does_not_back_a_chinese_test_claim(self) -> None:
        self.track(self.shell("git status --short"))
        self.assertNoticed(self.stop("全部 413 項測試通過。"),
                           "no test or build command")

    def test_git_status_after_an_edit_does_not_refresh_a_test_run(self) -> None:
        self.track(self.shell("pytest -q"))
        self.track(self.edit("src/app.py"))
        self.track(self.shell("git status"))
        self.assertNoticed(self.stop(CLAIM), "edited after the last test or build run")

    def test_a_test_run_after_the_last_edit_needs_no_notice(self) -> None:
        self.track(self.edit("src/app.py"))
        self.track(self.shell("python -m unittest discover -s tests"))
        self.track(self.shell("git status"))
        self.assertQuiet(self.stop(CLAIM))

    def test_a_build_run_backs_a_build_claim(self) -> None:
        self.track(self.shell("npm run build"))
        self.assertQuiet(self.stop("Done, the build passes."))

    def test_a_state_claim_needs_only_a_status_query(self) -> None:
        self.track(self.shell("git status"))
        self.assertQuiet(self.stop("Confirmed: the branch is clean and pushed."))

    def test_a_conditional_test_phrase_is_not_a_test_claim(self) -> None:
        for message in ("I will rebase once the tests pass.",
                        "測試通過後我會先 rebase。"):
            with self.subTest(message=message):
                self.track(self.shell("git status"))  # each Stop empties the ledger
                self.assertQuiet(self.stop(message))

    def test_the_second_pass_still_shows_the_notice(self) -> None:
        self.track(self.shell("git status"))
        self.assertNoticed(self.stop(CLAIM, stop_active=True), "no test or build command")

    def test_the_test_ledger_is_cleaned_up(self) -> None:
        self.track(self.shell("pytest -q"))
        self.stop(CLAIM)
        self.assertEqual(sorted(p.name for p in (self.home / "ledger").glob("flow.*")), [])

    def test_an_extra_test_command_can_be_configured(self) -> None:
        self.extra_env = {"CLAIM_GUARD_TEST_CMD": "mytestrunner"}
        self.track(self.shell("git status"))
        self.track(self.shell("mytestrunner --all"))
        self.assertQuiet(self.stop(CLAIM))

    def test_an_empty_ledger_still_blocks_a_test_claim(self) -> None:
        # The notice is added on top; the first-tier rule it sits on is not relaxed.
        self.assertBlocked(self.stop(CLAIM))

    # -- subagents: a ledger of their own, checked when the subagent stops --------
    # Claude Code and Codex send `agent_id` with a tool call made inside a subagent
    # and fire SubagentStop when it finishes. The subagent's calls are still written
    # to the parent's ledger (so the parent's Stop check is what it was) and also to
    # `<session>.<agent_id>.*`, which only that subagent's stop reads and removes.
    # Replayed on 1058 local subagent runs (2026-11-21): 26 would be flagged and
    # none of the 17 that the parent rules would stop was a real miss, so a
    # subagent finding is a notice and never stops the subagent.

    AGENT = "a1b2c3d4e5f60718"
    silent_when_untracked = False

    def in_agent(self, payload: dict, agent_id: str = AGENT) -> dict:
        payload = dict(payload)
        payload.update({"agent_id": agent_id, "agent_type": "general-purpose"})
        return payload

    def subagent_stop(self, message: str, agent_id: str = AGENT, stop_active: bool = False,
                      agent_type: str = "general-purpose", transcript: str = "") -> str:
        return self.call(self.guard_command, self.subagent_stop_payload(
            message, agent_id, stop_active, agent_type, transcript))

    def sub_files(self, agent_id: str = AGENT) -> list:
        return sorted(p.name for p in (self.home / "ledger").glob("flow.%s.*" % agent_id))

    def assertSubNoticed(self, output: str, text: str) -> None:
        self.assertAllowed(output)
        self.assertIn("subagent", self.notice(output))
        self.assertIn(text, self.notice(output))

    def test_a_subagent_claim_is_checked_against_its_own_ledger(self) -> None:
        # What was seen for real: the parent's ledger has evidence, the subagent ran
        # nothing that checks anything, and it reports "verified" all the same.
        self.track(self.shell("pytest -q"))
        self.track(self.in_agent(self.shell("ls tests/")))
        self.assertSubNoticed(self.subagent_stop("Fixed it. Verified on the live box."),
                              "no verification command")

    def test_a_subagent_stop_leaves_the_parent_ledger_alone(self) -> None:
        self.track(self.shell("pytest -q"))
        self.track(self.in_agent(self.shell("ls tests/")))
        self.subagent_stop(CLAIM)
        self.assertQuiet(self.stop(CLAIM))

    def test_a_parent_can_claim_what_its_subagent_ran(self) -> None:
        self.track(self.in_agent(self.shell("pytest -q")))
        self.assertQuiet(self.subagent_stop(CLAIM))
        self.assertQuiet(self.stop(CLAIM))

    def test_a_subagent_status_query_does_not_back_its_test_claim(self) -> None:
        self.track(self.in_agent(self.shell("git status")))
        self.assertSubNoticed(self.subagent_stop(CLAIM), "no test or build command")

    def test_a_subagent_edit_after_its_verification_is_noticed(self) -> None:
        self.track(self.in_agent(self.shell("pytest -q")))
        self.track(self.in_agent(self.edit("src/app.py")))
        self.assertSubNoticed(self.subagent_stop(CLAIM), "edited files after its last verification")
        self.assertBlocked(self.stop(CLAIM), "stale verification")  # the parent's rule is what it was

    def test_a_subagent_negative_claim_without_a_search_is_noticed(self) -> None:
        self.track(self.in_agent(self.shell("git status")))
        self.assertSubNoticed(self.subagent_stop("That option does not exist in the current release."),
                              "no search")

    def test_two_subagents_keep_separate_ledgers(self) -> None:
        self.track(self.in_agent(self.shell("pytest -q"), "aaaa1111"))
        self.track(self.in_agent(self.shell("ls tests/"), "bbbb2222"))
        self.assertSubNoticed(self.subagent_stop(CLAIM, agent_id="bbbb2222"), "no verification command")
        self.assertQuiet(self.subagent_stop(CLAIM, agent_id="aaaa1111"))

    def test_a_subagent_ledger_is_removed_at_its_own_stop_only(self) -> None:
        self.track(self.in_agent(self.shell("pytest -q")))
        self.stop("Still working on it.")  # the parent's turn ends while the subagent runs on
        self.assertNotEqual(self.sub_files(), [])
        self.assertQuiet(self.subagent_stop(CLAIM))
        self.assertEqual(self.sub_files(), [])

    def test_a_handback_report_is_checked(self) -> None:
        # Claude Code 2.1.271+: the report is the SubagentHandback call's `message`;
        # SubagentStop's last_assistant_message is only the closing text.
        self.track(self.in_agent(self.shell("ls tests/")))
        self.track(self.in_agent(self.tool("SubagentHandback", {"message": "Fixed. " + CLAIM})))
        self.assertSubNoticed(self.subagent_stop(""), "no verification command")
        self.assertEqual(self.sub_files(), [])

    def test_a_handback_report_is_read_from_the_subagent_transcript(self) -> None:
        transcript = self.home / ("agent-%s.jsonl" % self.AGENT)
        lines = [
            {"parentUuid": None, "isSidechain": True, "agentId": self.AGENT, "type": "user",
             "message": {"role": "user", "content": "Fix the parser."}, "sessionId": "flow"},
            {"parentUuid": "u1", "isSidechain": True, "agentId": self.AGENT, "type": "assistant",
             "message": {"role": "assistant", "content": [
                 {"type": "text", "text": "Reporting back."},
                 {"type": "tool_use", "id": "toolu_01", "name": "SubagentHandback",
                  "input": {"message": "Fixed the parser.\n" + CLAIM}}]}, "sessionId": "flow"},
        ]
        transcript.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
        self.track(self.in_agent(self.shell("ls tests/")))
        self.assertSubNoticed(self.subagent_stop("Done.", transcript=str(transcript)),
                              "no verification command")

    def test_a_subagent_that_ran_nothing_at_all(self) -> None:
        # Codex's documented PostToolUse fields do not promise agent_id; with no
        # ledger at all for the agent its builds cannot tell "ran nothing" from
        # "the tracker was never told", so they stay silent.
        output = self.subagent_stop("Fixed it. Verified on the live box.")
        if self.silent_when_untracked:
            self.assertQuiet(output)
        else:
            self.assertSubNoticed(output, "no verification command")

    def test_an_internal_agent_with_no_type_is_ignored(self) -> None:
        self.track(self.in_agent(self.shell("ls tests/")))
        self.assertQuiet(self.subagent_stop(CLAIM, agent_type=""))

    def test_a_subagent_stop_without_an_agent_id_touches_nothing(self) -> None:
        self.track(self.shell("pytest -q"))
        self.assertQuiet(self.subagent_stop(CLAIM, agent_id=""))
        self.assertQuiet(self.stop(CLAIM))

    def test_a_continued_subagent_is_not_checked_again(self) -> None:
        self.track(self.in_agent(self.shell("ls tests/")))
        self.assertQuiet(self.subagent_stop(CLAIM, stop_active=True))


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

    # Fields a Codex payload adds to Claude Code's (none for Claude Code itself).
    codex_fields: dict = {}

    def subagent_stop_payload(self, message: str, agent_id: str, stop_active: bool,
                              agent_type: str, transcript: str) -> dict:
        payload = {"session_id": "flow", "transcript_path": str(self.home / "flow.jsonl"),
                   "cwd": str(self.home), "permission_mode": "default",
                   "hook_event_name": "SubagentStop", "stop_hook_active": stop_active,
                   "agent_id": agent_id, "agent_type": agent_type,
                   "agent_transcript_path": transcript or None, "last_assistant_message": message}
        if self.codex_fields:
            payload.update(self.codex_fields)
        else:
            payload.update({"background_tasks": [], "session_crons": []})
        return payload


class CodexPythonLedgerFlow(ClaudePythonLedgerFlow):
    tracker_command = [sys.executable, str(TRACKER), "--codex"]
    codex_fields = {"turn_id": "flow", "model": "gpt-5"}
    silent_when_untracked = True

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


def load_tracker():
    spec = importlib.util.spec_from_file_location("claim_ledger_tracker", TRACKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Commands that run tests or a build (tier one) and commands that only look at
# state (tier two). Drawn from what the 2026-11-21 transcript sample actually ran.
TEST_OR_BUILD_COMMANDS = (
    "pytest -q",
    "cd repo && pytest tests/test_x.py",
    "uv run pytest",
    "python -m pytest -q",
    "python -m unittest discover -s tests -p \"test_*.py\"",
    "uv run --python 3.11 -m compileall scripts hooks",
    "python -c \"import py_compile; py_compile.compile('a.py')\"",
    "python hooks/claim-guard/tests/run-tests.py",
    "python hooks/tests/run-agent-protocol-tests.py",
    "python tests/test_fork_divergence.py",
    "python scripts/verify-install.py --agent all",
    "pwsh -NoProfile -File tools/dev_check.ps1",
    "bash tools/dev_check.sh",
    "& \"C:\\work\\tests\\Run-All.ps1\"",
    "./run-tests.sh",
    "Invoke-Pester -Path tests",
    "npm test",
    "npm run build -w @aihot/web",
    "npm run typecheck",
    "pnpm test",
    "yarn build",
    "bun test",
    "npx vitest run",
    "npx playwright test",
    "node --test apps/web/tests/a.test.ts",
    "npx tsc --noEmit",
    "deno test",
    "cargo test",
    "cd C:\\GitHub\\buzz; & \"$env:USERPROFILE\\.cargo\\bin\\cargo.exe\" check -p buzz-agent",
    "go test ./...",
    "go vet ./...",
    "dotnet test",
    "dotnet build -c Release",
    "mvn -q test",
    "./gradlew build",
    "make test",
    "bash -n hooks/x.sh",
    "gh run watch 123 --exit-status",
    "gh pr checks 42",
)
STATUS_QUERY_COMMANDS = (
    "git status",
    "git status --short",
    "git diff --stat",
    "git log --oneline -5",
    "git add tests/test_x.py",
    "ls tests/",
    "cat tests/test_x.py",
    "wc -l tests/run-tests.py",
    "grep -n pytest README.md",
    "pip install pytest",
    "Test-Path C:\\work\\a.txt",
    "Get-Process python",
    "Get-Command npm",
    "python --version",
    "python -c \"print(1)\"",
    "python -m json.tool a.json",
    "curl -sI https://example.invalid",
    "echo latest.py contest.py",
    "python tools/check_divergence.py",
)


class TestTierPatterns(unittest.TestCase):
    """Which commands count as a test or build run (the tracker's tier one)."""

    def test_test_and_build_commands_are_tier_one(self) -> None:
        tracker = load_tracker()
        for command in TEST_OR_BUILD_COMMANDS:
            with self.subTest(command=command):
                self.assertTrue(tracker.is_test_command(command))

    def test_status_queries_are_not_tier_one(self) -> None:
        tracker = load_tracker()
        for command in STATUS_QUERY_COMMANDS:
            with self.subTest(command=command):
                self.assertFalse(tracker.is_test_command(command))

    def test_an_invalid_extra_pattern_is_ignored(self) -> None:
        tracker = load_tracker()
        self.assertFalse(tracker.is_test_command("git status", extra="(unclosed"))
        self.assertTrue(tracker.is_test_command("pytest", extra="(unclosed"))

    def test_test_commands_still_count_only_where_they_did_for_verification(self) -> None:
        # Tier one is a separate ledger. It must not make anything count as
        # verification that did not count before.
        tracker = load_tracker()
        self.assertIsNone(tracker.VERIFY_CMD.search("python tools/check_divergence.py"))


class AntigravityTestTier(unittest.TestCase):
    """Antigravity's Stop allows with {} exactly, so the notice goes to stderr."""

    def test_status_only_then_a_test_claim_allows_with_a_notice_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("CLAIM_GUARD_TEST_CMD", None)
            env["CLAIM_GUARD_LEDGER_DIR"] = tmp
            env["HARNESS_GUARD_STATE_DIR"] = tmp
            transcript = Path(tmp) / "t.jsonl"
            transcript.write_text(json.dumps({"type": "PLANNER_RESPONSE", "text": "The tests pass."}) + "\n",
                                  encoding="utf-8")
            post = {"conversationId": "agy-tier", "workspacePaths": [tmp], "stepIdx": 2,
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}}
            subprocess.run([sys.executable, str(TRACKER)], input=json.dumps(post).encode("utf-8"),
                           env=env, capture_output=True, check=True)
            self.assertTrue((Path(tmp) / "agy-tier.verify").exists())
            self.assertFalse((Path(tmp) / "agy-tier.test").exists())
            stop = {"conversationId": "agy-tier", "workspacePaths": [tmp], "transcriptPath": str(transcript),
                    "terminationReason": "NO_TOOL_CALL"}
            proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(stop).encode("utf-8"),
                                  env=env, capture_output=True, check=True)
            self.assertEqual(proc.stdout.decode("utf-8").strip(), "{}")
            self.assertIn("no test or build command", proc.stderr.decode("utf-8"))

    def test_a_test_run_is_written_to_the_test_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["CLAIM_GUARD_LEDGER_DIR"] = tmp
            post = {"conversationId": "agy-tier", "workspacePaths": [tmp],
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "python -m pytest -q"}}}
            subprocess.run([sys.executable, str(TRACKER)], input=json.dumps(post).encode("utf-8"),
                           env=env, capture_output=True, check=True)
            self.assertIn("pytest", (Path(tmp) / "agy-tier.test").read_text(encoding="utf-8"))


class CursorTestTier(unittest.TestCase):
    """Cursor's stop cannot veto; a follow-up would start a new turn, so the notice stays off stdout."""

    def test_the_notice_is_not_sent_as_a_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("CLAIM_GUARD_TEST_CMD", None)
            env["CLAIM_GUARD_LEDGER_DIR"] = tmp
            post = {"conversation_id": "cur-tier", "hook_event_name": "afterShellExecution",
                    "cursor_version": "1.7", "command": "git status", "output": ""}
            subprocess.run([sys.executable, str(TRACKER)], input=json.dumps(post).encode("utf-8"),
                           env=env, capture_output=True, check=True)
            stop = {"conversation_id": "cur-tier", "hook_event_name": "stop", "cursor_version": "1.7",
                    "status": "completed", "last_assistant_message": CLAIM}
            proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(stop).encode("utf-8"),
                                  env=env, capture_output=True, check=True)
            self.assertNotIn("followup_message", proc.stdout.decode("utf-8"))
            self.assertIn("no test or build command", proc.stderr.decode("utf-8"))


@unittest.skipIf(os.name == "nt" or not shutil.which("jq"), "POSIX shell builds need bash and jq")
class ClaudeShellLedgerFlow(ClaudePythonLedgerFlow):
    tracker_command = ["bash", str(REPO / "hooks/claim-guard/claude-code/claim-ledger-tracker.sh")]
    guard_command = ["bash", str(REPO / "hooks/claim-guard/claude-code/claim-evidence-guard.sh")]


@unittest.skipIf(os.name == "nt" or not shutil.which("jq"), "POSIX shell builds need bash and jq")
class CodexShellLedgerFlow(ClaudePythonLedgerFlow):
    tracker_command = ["bash", str(REPO / "hooks/claim-guard/codex/claim-ledger-tracker.sh")]
    guard_command = ["bash", str(REPO / "hooks/claim-guard/codex/claim-evidence-guard.sh")]
    codex_fields = {"turn_id": "flow", "model": "gpt-5"}
    silent_when_untracked = True

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


class NotAClaimPatternParity(unittest.TestCase):
    """The POSIX builds strip exactly what the Python build strips.

    The jq copy cannot be run on a machine without jq, so this compares the
    pattern text itself: the jq string literal, decoded as the JSON string it
    is, must equal NOT_A_CLAIM.pattern.
    """

    def test_jq_pattern_matches_python(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "claim_evidence_guard_parity",
            REPO / "hooks" / "claim-guard" / "windows" / "claim_evidence_guard.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for script in ("claude-code/claim-evidence-guard.sh", "codex/claim-evidence-guard.sh"):
            with self.subTest(script=script):
                text = (REPO / "hooks" / "claim-guard" / script).read_text(encoding="utf-8")
                marker = "jq -Rrs 'gsub("
                start = text.index(marker) + len(marker)
                literal = text[start:text.index('"; " "; "i")', start) + 1]
                self.assertEqual(json.loads(literal), module.NOT_A_CLAIM.pattern)


def posix_bash():
    """Git Bash on Windows (a bare `bash` there may be WSL), else bash on PATH."""
    if os.name == "nt":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        return str(git_bash) if git_bash.exists() else None
    return shutil.which("bash")


def shell_block(script: Path, name: str) -> str:
    """The text between `# >>> name` and `# <<< name` in a shell script."""
    text = script.read_text(encoding="utf-8")
    start = text.index("# >>> %s\n" % name) + len("# >>> %s\n" % name)
    return text[start:text.index("# <<< %s" % name, start)]


SHELL_TRACKERS = ("claude-code/claim-ledger-tracker.sh", "codex/claim-ledger-tracker.sh")
SHELL_GUARDS = ("claude-code/claim-evidence-guard.sh", "codex/claim-evidence-guard.sh")


@unittest.skipIf(not posix_bash(), "needs bash (Git Bash on Windows)")
class ShellTestTierParity(unittest.TestCase):
    """The POSIX builds' grep -E patterns sort the same commands and claims as Python.

    The two dialects differ (no lookbehind, POSIX classes), so the patterns
    cannot be compared as text; they are run on the same samples instead. This
    needs bash and grep only, not jq, so it runs on Windows too.
    """

    def grep(self, block: str, var: str, samples, flags: str = "-qiE", pre: str = "") -> list:
        script = block + "\n" + (
            'while IFS= read -r -d "" s; do '
            'if printf "%%s" "$s" %s| grep %s -- "$%s"; then echo 1; else echo 0; fi; done' % (pre, flags, var))
        proc = subprocess.run([posix_bash(), "-c", script], input="\0".join(samples).encode("utf-8") + b"\0",
                              capture_output=True, check=True)
        return [line == "1" for line in proc.stdout.decode("utf-8").split()]

    def test_tracker_test_pattern(self) -> None:
        samples = TEST_OR_BUILD_COMMANDS + STATUS_QUERY_COMMANDS
        expected = [True] * len(TEST_OR_BUILD_COMMANDS) + [False] * len(STATUS_QUERY_COMMANDS)
        for script in SHELL_TRACKERS:
            with self.subTest(script=script):
                block = shell_block(REPO / "hooks" / "claim-guard" / script, "test-cmd-ere")
                got = self.grep(block, "TEST_CMD_ERE", samples)
                wrong = [s for s, g, e in zip(samples, got, expected) if g != e]
                self.assertEqual(wrong, [])

    def test_guard_test_claim_pattern(self) -> None:
        guard = load_guard()
        samples = (CLAIM, "Done, the build passes.", "全部 413 項測試通過。",
                   "All green.", "Confirmed: the branch is clean and pushed.", "Verified on the live box.",
                   "I will rebase once the tests pass.", "測試通過後我會先 rebase。")
        expected = [guard.is_test_claim(s) for s in samples]
        self.assertEqual(expected, [True, True, True, True, False, False, False, False])
        for script in SHELL_GUARDS:
            with self.subTest(script=script):
                block = shell_block(REPO / "hooks" / "claim-guard" / script, "test-claim-ere")
                got = self.grep(block, "TEST_CLAIM_ERE", samples, pre='| sed -E "$TEST_CLAIM_NOT_SED" ')
                self.assertEqual(got, expected)


def load_guard():
    spec = importlib.util.spec_from_file_location("claim_evidence_guard_tier", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(not posix_bash(), "needs bash (Git Bash on Windows)")
class PosixScriptsParse(unittest.TestCase):
    """Every POSIX hook script parses, whether or not jq is installed.

    The jq-backed tests above skip without jq, and a stray quote in a jq program
    once broke both claim-evidence-guard.sh builds outright (2026-11-09) with no
    test noticing. `bash -n` needs neither jq nor a payload.
    """

    def test_bash_n(self) -> None:
        for script in sorted((REPO / "hooks").glob("*/*/*.sh")):
            with self.subTest(script=str(script.relative_to(REPO))):
                proc = subprocess.run([posix_bash(), "-n", script.as_posix()],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
