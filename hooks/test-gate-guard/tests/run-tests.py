#!/usr/bin/env python3
"""Regression suite for test-gate-guard, both builds.

Run it with:  python hooks/test-gate-guard/tests/run-tests.py

Every case below is either a shape that must be blocked, or a false positive
this hook actually produced in service and must never produce again. The
heredoc and quoted-string cases are the second kind: a work log that merely
mentions `pytest ; git push` is text, not a command.

Expected result: 12 passed, 0 failed, for each build.
"""
import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
CLAUDE_HOOK = HOOKS_DIR / "claude-code" / "test_gate_guard.py"
CODEX_HOOK = HOOKS_DIR / "codex" / "test_gate_guard.py"

# (should_block, command)
CASES = [
    (True, "pytest ; git push"),
    (False, "pytest && git push"),
    (True, 'npm test\ngit commit -m "x"'),
    (False, 'git commit -m "docs: update"'),
    (False, 'git commit -m "fix pytest; flaky case"'),
    (False, "git commit -m x ; pytest"),
    (True, "cd repo && go test ./... ; git push origin main"),
    # False positives seen in service: text that mentions commands
    (False, "cat >> log.md << 'EOF'\n- ran pytest ; git push --dry-run\n- git commit note\nEOF\necho done"),
    (False, "echo 'pytest ; git push' > note.txt"),
    (False, 'echo "run pytest then git commit" && git commit -m x'),
    # Still a real hit once the quoted section is blanked out
    (True, 'pytest -k "slow ; case" ; git commit -m "wip"'),
    # Windows-native runner, same shape
    (True, "Invoke-Pester ; git push"),
    (True, "bun test ; git push"),
    (False, "bun test && git push"),
    (True, "playwright test ; git commit -m 'fix e2e'"),
    (False, "playwright test && git commit -m 'fix e2e'"),
    (True, "deno test ; git push"),
]


def run(hook, command, tool_name):
    payload = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(hook)], input=payload, capture_output=True, text=True
    )


def check(label, hook, tool_name, blocked_from):
    print("-- %s (%s)" % (label, hook.name))
    failures = 0
    for should_block, command in CASES:
        proc = run(hook, command, tool_name)
        blocked = blocked_from(proc)
        ok = blocked == should_block
        failures += not ok
        shown = command.replace("\n", "\\n")[:56]
        print(
            "%s expected=%-5s got=%-5s %s"
            % ("PASS" if ok else "FAIL", should_block, blocked, shown)
        )
    print("failures: %d\n" % failures)
    return failures


def main():
    total = 0
    if CLAUDE_HOOK.exists():
        total += check(
            "Claude Code build", CLAUDE_HOOK, "Bash", lambda p: p.returncode == 2
        )
    if CODEX_HOOK.exists():
        total += check(
            "Codex build",
            CODEX_HOOK,
            "shell",
            lambda p: '"block"' in p.stdout,
        )
    total += check_cursor_payload()
    print("total failures:", total)
    return 1 if total else 0


def check_cursor_payload():
    print("-- Cursor beforeShellExecution payload (%s)" % CLAUDE_HOOK.name)
    failures = 0
    for should_block, command in CASES:
        payload = json.dumps({
            "hook_event_name": "beforeShellExecution",
            "cursor_version": "1.0",
            "command": command,
        })
        proc = subprocess.run(
            [sys.executable, str(CLAUDE_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
        )
        blocked = '"permission": "deny"' in proc.stdout or proc.returncode == 2
        ok = blocked == should_block
        failures += not ok
        shown = command.replace("\n", "\\n")[:56]
        print(
            "%s expected=%-5s got=%-5s %s"
            % ("PASS" if ok else "FAIL", should_block, blocked, shown)
        )
    print("failures: %d\n" % failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
