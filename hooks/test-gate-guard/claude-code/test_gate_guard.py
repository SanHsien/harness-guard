#!/usr/bin/env python3
"""test_gate_guard.py -- blocks a commit that is chained after a test with `;`.

The failure it exists to stop, from a real incident: a single Bash call ran the
test suite and then pushed, joined with `;` instead of `&&`. The tests came
back red. `;` does not care -- the push went out anyway, and the wrap-up
message said the work was done.

What gets blocked: one Bash command where a test or check command comes first,
a `git commit` or `git push` comes later, and the separator between them is
`;` or a newline rather than `&&`. That combination means a red test still
commits.

What is deliberately NOT done: this hook never runs any tests itself. It cannot
know which framework a given repo uses, and guessing would produce false
failures and slow every call down. It only checks the shape of the command.

Known limit: it only sees one Bash call at a time. Splitting the work across
two tool calls (test first, push second) is not visible to it -- that is what
the exit code of the first call is for.

Register on PreToolUse with matcher `Bash`. Exit 0 lets the call through,
exit 2 blocks it and returns the stderr text to the assistant.

Cross-platform: pure standard library, no `jq`, no shell. Works the same on
Windows, macOS, and Linux.
"""
import json
import re
import sys

TEST_CMD = re.compile(
    r"\b("
    r"pytest|tox|nox"
    r"|npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+(?:run\s+)?test"
    r"|jest|vitest"
    r"|go\s+test|cargo\s+test|dotnet\s+test|mvn\s+test|gradle\s+test"
    r"|bundle\s+exec\s+rspec|rspec|phpunit"
    r"|Invoke-Pester"
    r"|make\s+(?:test|check)"
    r"|ruff\s+check|mypy|tsc\s+--noEmit"
    r")\b"
)
GIT_WRITE = re.compile(r"\bgit\s+(?:commit|push)\b")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

MESSAGE = (
    "TEST GATE: the test command `{test}` and `{git}` are joined with `;` or a "
    "newline, so the commit still runs when the tests come back red -- this is "
    "the exact shape of a real incident.\n"
    "Join them with `&&` instead, or split them into two tool calls and check "
    "that the first one exited 0 before committing.\n"
)


def strip_literals(command):
    """Blank out heredoc bodies and quoted strings -- those are data, not commands.

    This hook produced a false positive on its first day in service: a work-log
    heredoc whose body mentioned `pytest ; git push` was read as a real
    command. Blanking preserves length (spaces are written in place) so the
    before/after ordering test stays accurate.
    """
    chars = list(command)

    for match in HEREDOC.finditer(command):
        delimiter = match.group(2)
        body_start = command.find("\n", match.end())
        if body_start == -1:
            continue
        end_match = re.compile(
            r"^\s*" + re.escape(delimiter) + r"\s*$", re.MULTILINE
        ).search(command, body_start)
        body_end = end_match.start() if end_match else len(command)
        for i in range(body_start, body_end):
            if chars[i] != "\n":
                chars[i] = " "

    blanked = "".join(chars)
    out = list(blanked)
    quote = None
    for i, ch in enumerate(blanked):
        if quote is None:
            if ch in "'\"":
                quote = ch
        elif ch == quote:
            quote = None
        else:
            out[i] = " "
    return "".join(out)


def verdict(command):
    """Return the (test, git) pair that should be blocked, or None."""
    command = strip_literals(command)
    for git_match in GIT_WRITE.finditer(command):
        head = command[: git_match.start()]
        test_matches = list(TEST_CMD.finditer(head))
        if not test_matches:
            continue
        separator = head[test_matches[-1].end():]
        if "&&" in separator:
            continue  # already gated
        if ";" not in separator and "\n" not in separator:
            continue  # not a chain
        return test_matches[-1].group(0), git_match.group(0)
    return None


def main():
    try:  # a Windows console defaults to cp950; force UTF-8 so output survives
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0  # unreadable input is never a reason to get in the way
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    hit = verdict(command)
    if hit:
        sys.stderr.write(MESSAGE.format(test=hit[0], git=hit[1]))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
