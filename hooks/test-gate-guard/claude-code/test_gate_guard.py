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
    r"|npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+(?:run\s+)?test|bun\s+(?:test|run\s+test)|deno\s+test"
    r"|jest|vitest|playwright\s+test|cypress\s+run"
    r"|go\s+test|cargo\s+test|dotnet\s+test|mvn\s+test|gradle\s+test|swift\s+test|mix\s+test"
    r"|bundle\s+exec\s+rspec|rspec|phpunit"
    r"|Invoke-Pester"
    r"|make\s+(?:test|check)"
    r"|ruff\s+check|mypy|flake8|eslint|tsc(?:\s+--noEmit)?"
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


def read_payload():
    """Read the hook payload as bytes and decode UTF-8 explicitly.

    `json.load(sys.stdin)` decodes using whatever encoding the locale hands the
    process. Where that is not UTF-8 -- the default on a Chinese, Japanese, or
    Korean Windows install -- any non-ASCII text in the payload is mangled, the
    JSON fails to parse, and the hook fails open. Silently, and precisely when
    the message or the command is not in English.

    Observed in service on 2026-08-15: a 2.3 KB Stop payload parsed as an empty
    object, so claim-evidence-guard saw no assistant message and let the turn
    end. Reading bytes removes the dependency on the ambient locale entirely.
    """
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        return {}
    return json.loads(raw.decode("utf-8", "replace"))


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
    try:
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    tool_name = (
        payload.get("tool_name")
        or (payload.get("toolCall") or {}).get("name")
        or ""
    )
    if tool_name not in ("Bash", "Exec", "exec", "shell", "run_command"):
        if "toolCall" in payload:
            sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0

    tool_input = (
        payload.get("tool_input")
        or (payload.get("toolCall") or {}).get("args")
        or {}
    )
    command = (
        tool_input.get("command")
        or tool_input.get("CommandLine")
        or tool_input.get("cmd")
        or ""
    )
    if not command:
        if "toolCall" in payload:
            sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0

    hit = verdict(command)
    if hit:
        msg = MESSAGE.format(test=hit[0], git=hit[1])
        if "toolCall" in payload:
            sys.stdout.write(json.dumps({"decision": "deny", "reason": msg}, ensure_ascii=False))
            return 0
        sys.stderr.write(msg)
        return 2

    if "toolCall" in payload:
        sys.stdout.write(json.dumps({"decision": "allow"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
