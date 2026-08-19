#!/usr/bin/env python3
"""Each hook must answer in the protocol of the agent that called it.

    python hooks/tests/run-agent-protocol-tests.py

Three agents, three different ways of saying "no":

  Claude Code   exit 2, message on stderr (Stop guards may also print a
                decision object)
  Cursor        exit 0 plus JSON -- `permission: deny` before an action, or a
                `followup_message`, because Cursor's stop cannot veto a turn
                that already finished
  Codex         exit 0 plus JSON -- `{}` to allow, {"decision": "block"} to stop

Why this suite exists. Cursor support identified the caller with
`payload.get("hook_event_name")`, which Claude Code also sends. Every realistic
Claude payload therefore looked like Cursor, and the two Stop guards --
claim-evidence-guard and lint-gate, the ones whose whole job is refusing to let
a turn end -- answered with a Cursor follow-up that Claude Code does not act
on. Registered, loaded, and no longer blocking anything.

The existing suites missed it because their synthetic payloads omit
`hook_event_name`. These use payloads shaped like the real thing.

Expected: 12 passed, 0 failed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent
CWD = str(HOOKS.parent)
LINT_ARGS = (
    "--cmd", "%s -c \"print('found 3 errors')\"" % sys.executable,
    "--fail", "[1-9][0-9]* errors?",
)


def run(hook, payload, args=()):
    env = dict(os.environ, CLAIM_GUARD_LEDGER_DIR=tempfile.mkdtemp())
    proc = subprocess.run(
        [sys.executable, str(hook)] + list(args),
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        env=env,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()


def blocks_for_claude(code, out):
    return code == 2 or '"decision": "block"' in out or '"decision":"block"' in out


def speaks_cursor(code, out):
    """Cursor reads the JSON on stdout.

    The exit code is deliberately not asserted here. Cursor's own handling of a
    non-zero exit from a hook is not documented anywhere this suite can check,
    and the before-action guards currently print the deny object *and* exit 2.
    If Cursor honours the JSON that is a correct deny; if it treats non-zero as
    a hook error it fails towards refusing, not towards allowing. Pinning a
    number here would be asserting something nobody verified."""
    return "followup_message" in out or '"permission"' in out


def speaks_codex(code, out):
    return code == 0 and out.startswith("{")


CASES = [
    # (label, hook path, payload, args, predicate)
    ("claim-evidence-guard blocks a Claude Stop",
     "claim-guard/windows/claim_evidence_guard.py",
     {"session_id": "p1", "cwd": CWD, "hook_event_name": "Stop",
      "last_assistant_message": "all tests pass"}, (), blocks_for_claude),
    ("lint-gate blocks a Claude Stop",
     "lint-gate/windows/lint_gate.py",
     {"session_id": "p1", "cwd": CWD, "hook_event_name": "Stop",
      "stop_hook_active": False}, LINT_ARGS, blocks_for_claude),
    ("danger-zone-guard blocks a Claude PreToolUse",
     "danger-zone-guard/claude-code/danger_zone_guard.py",
     {"session_id": "p1", "cwd": CWD, "hook_event_name": "PreToolUse",
      "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, (), blocks_for_claude),
    ("test-gate-guard blocks a Claude PreToolUse",
     "test-gate-guard/claude-code/test_gate_guard.py",
     {"session_id": "p1", "cwd": CWD, "hook_event_name": "PreToolUse",
      "tool_name": "Bash", "tool_input": {"command": "pytest ; git push"}}, (), blocks_for_claude),
    ("no-emoji-guard blocks a Claude PreToolUse",
     "no-emoji-guard/claude-code/no-emoji-guard.py",
     {"session_id": "p1", "cwd": CWD, "hook_event_name": "PreToolUse", "tool_name": "Write",
      "tool_input": {"file_path": "a.md", "content": "done \U0001F680"}}, (), blocks_for_claude),

    ("claim-evidence-guard follows up for Cursor",
     "claim-guard/windows/claim_evidence_guard.py",
     {"session_id": "p2", "cwd": CWD, "hook_event_name": "stop", "cursor_version": "1.0",
      "last_assistant_message": "all tests pass"}, (), speaks_cursor),
    ("lint-gate follows up for Cursor",
     "lint-gate/windows/lint_gate.py",
     {"cursor_version": "1.0", "hook_event_name": "stop",
      "workspace_roots": [CWD]}, LINT_ARGS, speaks_cursor),
    ("danger-zone-guard denies for Cursor",
     "danger-zone-guard/claude-code/danger_zone_guard.py",
     {"hook_event_name": "beforeShellExecution", "cursor_version": "1.0",
      "command": "rm -rf /"}, (), speaks_cursor),

    ("danger-zone-guard speaks Codex",
     "danger-zone-guard/codex/danger_zone_guard.py",
     {"tool_name": "exec", "tool_input": {"command": "rm -rf /"}}, (), speaks_codex),
    ("test-gate-guard speaks Codex",
     "test-gate-guard/codex/test_gate_guard.py",
     {"tool_name": "shell", "tool_input": {"command": "pytest ; git push"}}, (), speaks_codex),
    # Two hooks have no jq-free Codex build, so the installer registers the
    # Windows build with --codex and it answers in Codex's protocol instead.
    ("lint-gate speaks Codex with --codex",
     "lint-gate/windows/lint_gate.py",
     {"cwd": CWD, "stop_hook_active": False}, LINT_ARGS + ("--codex",), speaks_codex),
    ("claim-ledger-tracker speaks Codex with --codex",
     "claim-guard/windows/claim_ledger_tracker.py",
     {"session_id": "p3", "tool_name": "exec",
      "tool_input": {"command": "pytest -q"}}, ("--codex",), speaks_codex),
]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    failures = 0
    for label, rel, payload, args, predicate in CASES:
        hook = HOOKS / rel
        if not hook.exists():
            print("SKIP %s -- %s not found" % (label, rel))
            continue
        code, out = run(hook, payload, args)
        ok = predicate(code, out)
        failures += not ok
        print("%-4s %-46s exit=%d %s" % (
            "PASS" if ok else "FAIL", label, code, "" if ok else "stdout=%r" % out[:70]))

    print("\nfailures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
