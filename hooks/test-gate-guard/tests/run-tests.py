#!/usr/bin/env python3
"""Regression suite for test-gate-guard, both builds.

Run it with:  python hooks/test-gate-guard/tests/run-tests.py

Every case below is either a shape that must be blocked, or a false positive
this hook actually produced in service and must never produce again. The
heredoc and quoted-string cases are the second kind: a work log that merely
mentions `pytest ; git push` is text, not a command.

Expected result: no failures, for each build.
"""
import json
import subprocess
import sys
import time
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
    # An `&&` elsewhere in the chain does not gate a commit that follows `;`
    (True, "pytest && echo ok ; git commit -m x"),
    (True, "pytest ; ls && git push"),
    # git options before the subcommand
    (True, "pytest ; git -C repo push"),
    (True, "pytest ; git -c user.name=x commit -m x"),
    (True, "pytest ; git --no-pager push"),
    (True, 'pytest ; git -C "my repo" push'),
    (False, "pytest && git -C repo push"),
    # Repeated `-C` must still resolve (and, see check_redos, in linear time)
    (True, "pytest ; git -C -C -C push"),
    (True, "pytest ; git -C a -C b -a=c --no-pager commit -m x"),
    (False, "pytest && git -C -C -C push"),
    # A here-string is not a heredoc; it must not hide what follows
    (True, "cat <<<hi\npytest ; git push"),
    # Escaped quotes do not open or close a string
    (True, 'echo \\"; pytest ; git push'),
    (False, 'echo "a \\" ; pytest ; git push"'),
    # A newline after an operator continues the command
    (False, "pytest &&\n git push"),
    (False, "pytest \\\n -x && git push"),
    (True, "pytest ||\n git push"),
]


# PowerShell only: a backslash is a path character there, so a quoted Windows
# path ending in one must not keep the string open and hide what follows.
POWERSHELL_CASES = [
    (True, 'Invoke-Pester -Path "C:\\repo\\tests\\" ; git push'),
    (True, 'pytest "C:\\repo\\" ; git commit -m x'),
    (False, 'Invoke-Pester -Path "C:\\repo\\tests\\" && git push'),
    (False, 'git commit -m "note `" ; pytest ; git push"'),
    (False, 'pytest `\n -x && git push'),
]


# Backslash escapes quotes and continues lines in POSIX shells only; PowerShell
# uses a backtick.
BASH_ONLY = {
    'echo \\"; pytest ; git push',
    'echo "a \\" ; pytest ; git push"',
}
# Line continuation by a trailing backslash is POSIX-only too, but callers that do
# not name their shell must still accept either continuation character.
CONTINUATION_CASES = ["pytest \\\n -x && git push", "pytest `\n -x && git push"]
# Codex, Cursor and Antigravity do not name their shell, so the hook reads their
# commands both ways and blocks on either hit. These cases are ambiguous there.


def run(hook, command, tool_name, timeout=None):
    payload = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(hook)], input=payload, capture_output=True, text=True,
        timeout=timeout,
    )


def check(label, hook, tool_name, blocked_from):
    print("-- %s (%s)" % (label, hook.name))
    failures = 0
    for should_block, command in CASES:
        if tool_name in ("PowerShell", "shell") and command in BASH_ONLY:
            continue
        if tool_name == "PowerShell" and command == CONTINUATION_CASES[0]:
            continue
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
        # Claude Code's PowerShell tool on Windows, where `;` is the usual separator.
        total += check(
            "Claude Code build, PowerShell tool", CLAUDE_HOOK, "PowerShell",
            lambda p: p.returncode == 2,
        )
    total += check_powershell_paths()
    total += check_unknown_shell()
    if CODEX_HOOK.exists():
        total += check(
            "Codex build",
            CODEX_HOOK,
            "shell",
            lambda p: '"block"' in p.stdout,
        )
    total += check_cursor_payload()
    total += check_redos()
    print("total failures:", total)
    return 1 if total else 0


def check_powershell_paths():
    print("-- PowerShell tool, backslash paths (%s)" % CLAUDE_HOOK.name)
    failures = 0
    for should_block, command in POWERSHELL_CASES:
        blocked = run(CLAUDE_HOOK, command, "PowerShell").returncode == 2
        ok = blocked == should_block
        failures += not ok
        print("%s expected=%-5s got=%-5s %s"
              % ("PASS" if ok else "FAIL", should_block, blocked, command[:56]))
    print("failures: %d\n" % failures)
    return failures


# Callers that do not say which shell they run (Codex, Cursor, Antigravity) get
# both readings, so a PowerShell path ending in a backslash cannot hide a push.
UNKNOWN_SHELL_COMMAND = 'Invoke-Pester -Path "C:\\repo\\tests\\" ; git push'


def check_unknown_shell():
    print("-- callers that do not name their shell")
    failures = 0
    payloads = [
        ("Cursor", CLAUDE_HOOK, {"hook_event_name": "beforeShellExecution",
                                 "cursor_version": "1.0", "command": UNKNOWN_SHELL_COMMAND}),
        ("Antigravity", CLAUDE_HOOK, {"toolCall": {"name": "run_command",
                                                   "args": {"CommandLine": UNKNOWN_SHELL_COMMAND}},
                                      "conversationId": "c"}),
        ("Codex", CODEX_HOOK, {"tool_name": "shell",
                               "tool_input": {"command": UNKNOWN_SHELL_COMMAND}}),
    ]
    for command in CONTINUATION_CASES:
        payloads.append(("Cursor, continued line", CLAUDE_HOOK, {
            "hook_event_name": "beforeShellExecution", "cursor_version": "1.0",
            "command": command, "_allow": True}))
        payloads.append(("Codex, continued line", CODEX_HOOK, {
            "tool_name": "shell", "tool_input": {"command": command}, "_allow": True}))
    for name, hook, payload in payloads:
        allow = payload.pop("_allow", False)
        if not hook.exists():
            continue
        proc = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                              capture_output=True, text=True)
        blocked = (proc.returncode == 2 or '"block"' in proc.stdout
                   or '"decision": "deny"' in proc.stdout)
        ok = blocked != allow
        failures += not ok
        print("%s %s %s" % ("PASS" if ok else "FAIL", name,
                            "allows" if allow else "blocks the backslash-path chain"))
    print("failures: %d\n" % failures)
    return failures


def check_redos():
    """A long run of `-C` after `git` must not stall the hook (CodeQL py/redos).

    The old option pattern parsed `git -C -C -C ...` in exponentially many ways, so
    ~50k characters of it hung the hook on every shell command. Each build must
    finish well inside the timeout, and must still block a real chained push.
    """
    print("-- ReDoS: adversarial git option runs")
    failures = 0
    runs = {
        "dash-C run": "-C " * 17000,
        "dash-C/option mix": "-C -a " * 8500,
        "quoted -C run": '-C " " ' * 8500,
    }
    for hook in (CLAUDE_HOOK, CODEX_HOOK):
        if not hook.exists():
            continue
        tool = "Bash" if hook is CLAUDE_HOOK else "shell"
        for label, run_of_opts in runs.items():
            for tail, should_block in (("x", False), ("push", True)):
                command = "pytest ; git " + run_of_opts + tail
                started = time.monotonic()
                try:
                    proc = run(hook, command, tool, timeout=10)
                except subprocess.TimeoutExpired:
                    print("FAIL %s %s: no verdict within 10s (ReDoS)" % (hook.parent.name, label))
                    failures += 1
                    continue
                elapsed = time.monotonic() - started
                blocked = proc.returncode == 2 or '"block"' in proc.stdout
                ok = blocked == should_block and elapsed < 10
                failures += not ok
                print("%s %s %s tail=%s blocked=%s %.2fs"
                      % ("PASS" if ok else "FAIL", hook.parent.name, label, tail, blocked, elapsed))
    print("failures: %d\n" % failures)
    return failures


def check_cursor_payload():
    print("-- Cursor beforeShellExecution payload (%s)" % CLAUDE_HOOK.name)
    failures = 0
    for should_block, command in CASES:
        if command in BASH_ONLY:
            continue
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
