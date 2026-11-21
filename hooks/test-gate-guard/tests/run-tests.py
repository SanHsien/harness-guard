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


# -- A gate that cannot close ------------------------------------------------
# `&&` is only a gate when the thing on its left exits non-zero on a red run.
# From a real incident (2026-11-21): `python -m unittest ... | tail -1 && git
# commit ...`. The pipeline's exit status is `tail`'s, so the commit ran on red
# and the `;` rule above saw a clean `&&` chain.
#
# (should_block, command) for a POSIX shell.
MASKED_POSIX_CASES = [
    (True, "python -m unittest discover -s tests 2>&1 | tail -1 && git commit -m x"),
    (True, "pytest | tail -5 && git push"),
    (True, "pytest 2>&1 | tail -5 && git commit -m x"),
    # A last stage that can only match a green run is a gate of its own.
    (False, "pytest -q | grep -c passed && git commit -m x"),
    (False, "python -m unittest 2>&1 | tail -1 | grep -q '^OK' && git push"),
    (False, "bun test 2>&1 | grep -qE '^ *0 fail' && git commit -m x"),
    (False, 'bun test 2>&1 | grep -E "^ *[0-9]+ fail" | grep -q "^ *0 fail" && git push'),
    # A grep that also matches a red run is a filter, not a check.
    (True, 'python -m unittest 2>&1 | grep -E "^(Ran|OK|FAILED)" && git commit -m x'),
    (True, 'python -m unittest 2>&1 | grep -E "^(OK|FAIL|ERROR)" && git commit -m x'),
    (True, "pytest 2>&1 | grep -v warning && git push"),
    (True, 'pytest | grep "Tests " && git push'),
    (True, "pytest | grep -q '^OK' | tail -1 && git push"),
    (True, "pytest |& tee log.txt && git push"),
    (True, "pytest | tee log.txt | tail -3 && git push"),
    (True, "cd repo && pytest | head -20 && git add -A && git commit -m x"),
    # An earlier test in the same chain is just as ungated as the last one.
    (True, "pytest | tail -3 && ruff check . && git commit -m x"),
    (True, "npm test 2>&1 | tail -20 &&\n git push"),
    (True, "out=$(pytest | tail -1) && git commit -m x"),
    (True, "python hooks/test-gate-guard/tests/run-tests.py | tail -2 && git commit -m x"),
    (True, "node --test | tail -4 && git push"),
    # pipefail makes the pipeline report the failing stage, so the gate holds.
    (False, "set -o pipefail; pytest | tail -5 && git commit -m x"),
    (False, "set -euo pipefail\npytest 2>&1 | tail -5 && git push"),
    (False, "set -eo pipefail && pytest | tail -5 && git push"),
    (True, "set -o pipefail; set +o pipefail; pytest | tail -5 && git push"),
    # Setting it after the test ran does nothing for that pipeline.
    (True, "pytest | tail -5 && set -o pipefail && git push"),
    # A redirect is not a pipe: the exit status is still the test's.
    (False, "pytest > test.log 2>&1 && tail -5 test.log && git commit -m x"),
    (False, "pytest > /dev/null 2>&1 && git push"),
    (False, "pytest >| out.log && git push"),
    (False, "pytest 2>&1 && git push"),
    # A pipe in a different link of the chain does not touch the test's status.
    (False, "pytest && git log --oneline | head -3 && git push"),
    (False, "git status | head -5 && pytest && git commit -m x"),
    # The test is the last stage, so its status is the pipeline's.
    (False, "cat list.txt | xargs pytest && git commit -m x"),
    (False, 'echo "pytest | tail && x" && git commit -m x'),
    (False, "cat >> log.md << 'EOF'\npytest | tail -1 && git commit\nEOF\ngit commit -m x"),
    # An earlier, separate statement is not part of this chain.
    (False, "pytest | tail -3\necho done\npytest && git push"),
]

# `||` after the test turns a red run into a success for the rest of the chain.
# Same in both shells. `exit`, `return`, `false` and `throw` keep the gate shut.
SWALLOWED_CASES = [
    (True, "pytest || true && git commit -m x"),
    (True, "pytest || echo failed && git push"),
    (True, "pytest || : && git push"),
    (True, "python -m unittest || true && git commit -m x"),
    (True, "pytest || git push"),
    (False, "pytest || exit 1 && git commit -m x"),
    (False, "pytest || exit && git push"),
    (False, "pytest || return 1 && git push"),
    (False, "pytest || false && git push"),
    (False, "pytest && git push || echo push-failed"),
    (False, "git pull || true && pytest && git push"),
    # Seen in service: the `||` sits inside a group that the tests still gate.
    (False, "pytest > /dev/null 2>&1 && echo OK && (git diff --quiet || (git add -A && git commit -m x))"),
    (True, "pytest && ruff check . || true && git push"),
    (True, "(pytest || true) && git push"),
]

# PowerShell 7: `&&` reads `$?`, and a native command that exits non-zero leaves
# `$?` false wherever it sits in the pipeline -- measured on 7.7.0 with
# Select-Object -Last, Out-String, Out-Null, Select-String, Tee-Object,
# ForEach-Object, Where-Object, Measure-Object, Out-File and a native `tail`.
# The exceptions: Select-Object -First / -Index stops the upstream command before
# it can report an exit code, and `(native) | ...` turns the call into an
# expression whose `$?` is true.
MASKED_POWERSHELL_CASES = [
    (False, "pytest | Select-Object -Last 5 && git commit -m x"),
    (False, "pytest 2>&1 | Out-String && git push"),
    (False, "pytest | tail -5 && git push"),
    (False, "python -m unittest 2>&1 | Select-String FAILED && git push"),
    (False, "pytest | Tee-Object -FilePath t.log | Select-Object -Last 3 && git push"),
    (True, "pytest | Select-Object -First 5 && git push"),
    (True, "pytest 2>&1 | select -f 20 && git commit -m x"),
    (True, "pytest | Select-String FAILED | Select-Object -First 1 && git push"),
    (True, "pytest | Select-Object -Index 0 && git push"),
    (True, "python -m unittest 2>&1 | Select-Object -First 30 && git commit -m x"),
    (True, "(pytest) | Select-Object -Last 5 && git push"),
    (True, "pytest || $true && git push"),
    (True, "pytest || Write-Output failed && git commit -m x"),
    (False, "pytest || exit 1 && git push"),
    (False, 'pytest || throw "red" && git push'),
    (False, "pytest -k (a) | Select-Object -Last 5 && git push"),
]

# Callers that do not name their shell (Codex, Cursor, Antigravity, Hermes): a
# hit under either reading blocks, except when every stage after the test is a
# PowerShell cmdlet -- that pipeline cannot be a POSIX one.
MASKED_UNKNOWN_CASES = [
    (True, "pytest | tail -5 && git push"),
    (True, "python -m unittest 2>&1 | tail -1 && git commit -m x"),
    (False, "pytest | Select-Object -Last 5 && git push"),
    (False, "pytest 2>&1 | Out-String && git push"),
    (True, "pytest | Select-Object -First 5 && git push"),
    (True, "pytest | Select-Object -Last 5 | tail -1 && git push"),
    (False, "set -o pipefail; pytest | tail -5 && git push"),
    (True, "pytest || true && git push"),
    (False, "pytest > test.log 2>&1 && git push"),
]

# The `;` rule only knew the runners in its first list. The incident's runner was
# `python -m unittest`, which that list did not have -- so `;` let it through too.
WIDENED_RUNNER_CASES = [
    (True, "python -m unittest discover -s tests ; git commit -m x"),
    (True, "py -3 -m unittest\ngit push"),
    (True, "python hooks/tests/run-tests.py ; git push"),
    (True, "bash scripts/run_tests.sh ; git commit -m x"),
    (True, "node --test ; git push"),
    (False, "python -m unittest discover -s tests && git commit -m x"),
    (False, "python hooks/tests/run-tests.py && git push"),
    (False, 'git commit -m "python -m unittest ; note"'),
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
    if CODEX_HOOK.exists():
        total += check_codex_tool_names()
    total += check_cursor_payload()
    total += check_masked_gate()
    total += check_builds_agree()
    total += check_redos()
    print("total failures:", total)
    return 1 if total else 0


def _fire(hook, payload):
    return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                          capture_output=True, text=True)


def _blocked(proc):
    return (proc.returncode == 2 or '"block"' in proc.stdout
            or '"decision": "deny"' in proc.stdout or '"permission": "deny"' in proc.stdout)


def _callers(shell):
    """(label, hook, payload builder) for every caller that reads `shell`."""
    if shell == "posix":
        return [("Claude Bash", CLAUDE_HOOK,
                 lambda c: {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                            "tool_input": {"command": c}})]
    if shell == "powershell":
        return [("Claude PowerShell", CLAUDE_HOOK,
                 lambda c: {"hook_event_name": "PreToolUse", "tool_name": "PowerShell",
                            "tool_input": {"command": c}})]
    return [
        ("Codex", CODEX_HOOK,
         lambda c: {"hook_event_name": "PreToolUse", "tool_name": "shell_command",
                    "tool_input": {"command": c}}),
        ("Cursor", CLAUDE_HOOK,
         lambda c: {"hook_event_name": "beforeShellExecution", "cursor_version": "1.0",
                    "command": c}),
        ("Antigravity", CLAUDE_HOOK,
         lambda c: {"toolCall": {"name": "run_command", "args": {"CommandLine": c}},
                    "conversationId": "c"}),
    ]


def check_masked_gate():
    """`&&` after a pipeline or a `||` is not a gate. See the case lists."""
    print("-- a gate that cannot close: pipes, `||`, widened runner list")
    failures = 0
    groups = [
        ("posix", MASKED_POSIX_CASES),
        ("posix", SWALLOWED_CASES),
        ("posix", WIDENED_RUNNER_CASES),
        ("powershell", MASKED_POWERSHELL_CASES),
        ("powershell", SWALLOWED_CASES),
        ("powershell", WIDENED_RUNNER_CASES),
        (None, MASKED_UNKNOWN_CASES),
        (None, SWALLOWED_CASES),
        (None, WIDENED_RUNNER_CASES),
    ]
    for shell, cases in groups:
        for label, hook, build in _callers(shell):
            if not hook.exists():
                continue
            for should_block, command in cases:
                blocked = _blocked(_fire(hook, build(command)))
                ok = blocked == should_block
                failures += not ok
                print("%s %-17s expected=%-5s got=%-5s %s" % (
                    "PASS" if ok else "FAIL", label, should_block, blocked,
                    command.replace("\n", "\\n")[:60]))
    failures += check_masked_messages()
    print("failures: %d\n" % failures)
    return failures


def check_builds_agree():
    """Both builds carry their own copy of the judging code; it must be one text."""
    print("-- the two builds judge with the same code")
    if not CODEX_HOOK.exists():
        print("failures: 0\n")
        return 0

    def judging(path):
        text = path.read_text(encoding="utf-8")
        begin = text.index("# -- A gate that cannot close")
        end = text.index("def _verdict(", begin)
        end = text.index("\n\n\n", end)
        patterns = text[text.index("TEST_CMD = re.compile("):text.index("# Options git accepts")]
        return patterns + text[begin:end]

    same = judging(CLAUDE_HOOK) == judging(CODEX_HOOK)
    print("%s TEST_CMD and the gate rules are identical in both files" % ("PASS" if same else "FAIL"))
    print("failures: %d\n" % (not same))
    return int(not same)


def check_masked_messages():
    """The block has to say how to write it so that it passes."""
    failures = 0
    wanted = [
        ("Bash", "pytest | tail -5 && git push", ("pipefail", "test.log")),
        ("PowerShell", "pytest | Select-Object -First 5 && git push", ("-Last", "test.log")),
        ("Bash", "pytest || true && git push", ("||",)),
        ("Bash", "pytest ; git push", ("&&",)),
    ]
    for tool, command, needles in wanted:
        proc = run(CLAUDE_HOOK, command, tool)
        ok = proc.returncode == 2 and all(n in proc.stderr for n in needles)
        failures += not ok
        print("%s message for `%s` names %s" % ("PASS" if ok else "FAIL", command, ", ".join(needles)))
    if CODEX_HOOK.exists():
        proc = run(CODEX_HOOK, "pytest | tail -5 && git push", "shell")
        try:
            reason = json.loads(proc.stdout).get("reason", "")
        except ValueError:
            reason = ""
        ok = "pipefail" in reason and "test.log" in reason
        failures += not ok
        print("%s Codex reason names pipefail and the log-file form" % ("PASS" if ok else "FAIL"))
    return failures


def check_codex_tool_names():
    """Every tool name the installer's Codex matcher lets through must be read.

    `shell_command` is in the matcher install.py registers, and was missing from
    the Codex build's own list -- so the hook ran and answered "allow" unread.
    """
    print("-- Codex build: tool names from the matcher (%s)" % CODEX_HOOK.name)
    failures = 0
    red = "pytest; git commit -m x"
    green = "pytest && git commit -m x"
    for tool in ("exec", "shell", "exec_command", "shell_command", "local_shell", "Bash"):
        for key in ("command", "cmd"):
            for command, should_block in ((red, True), (green, False)):
                payload = json.dumps({"tool_name": tool, "tool_input": {key: command}})
                proc = subprocess.run(
                    [sys.executable, str(CODEX_HOOK)], input=payload, capture_output=True, text=True,
                )
                blocked = '"block"' in proc.stdout
                ok = blocked == should_block and proc.returncode == 0
                failures += not ok
                print("%s expected=%-5s got=%-5s %s/%s" % (
                    "PASS" if ok else "FAIL", should_block, blocked, tool, key))
    payload = json.dumps({"tool_name": "shell", "tool_input": {"command": ["bash", "-lc", red]}})
    proc = subprocess.run([sys.executable, str(CODEX_HOOK)], input=payload, capture_output=True, text=True)
    ok = '"block"' in proc.stdout
    failures += not ok
    print("%s argv list is read" % ("PASS" if ok else "FAIL"))
    print("failures: %d\n" % failures)
    return failures


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
