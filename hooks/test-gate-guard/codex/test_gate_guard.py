#!/usr/bin/env python3
"""test_gate_guard.py (Codex build) -- blocks a commit chained after a test with `;`.

Identical judging logic to the Claude Code build in the sibling folder. Only
the interface differs, per the table in hooks/README.md:

  - allowing something prints `{}` rather than exiting quietly
  - a block is expressed as {"decision":"block","reason":"..."} on stdout,
    not exit 2 plus stderr
  - the command-running tool may arrive under several names, so all of them
    are accepted

Read the Claude Code build for the full reasoning and the known limits.

Register on PreToolUse in ~/.codex/hooks.json (and set `hooks = true` in
~/.codex/config.toml).
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
SHELL_TOOLS = ("Bash", "shell", "exec", "exec_command")

MESSAGE = (
    "TEST GATE: the test command `{test}` and `{git}` are joined with `;` or a "
    "newline, so the commit still runs when the tests come back red -- this is "
    "the exact shape of a real incident. Join them with `&&` instead, or split "
    "them into two calls and check that the first one exited 0 before "
    "committing."
)


def strip_literals(command):
    """Blank out heredoc bodies and quoted strings -- those are data, not commands."""
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
    command = strip_literals(command)
    for git_match in GIT_WRITE.finditer(command):
        head = command[: git_match.start()]
        test_matches = list(TEST_CMD.finditer(head))
        if not test_matches:
            continue
        separator = head[test_matches[-1].end():]
        if "&&" in separator:
            continue
        if ";" not in separator and "\n" not in separator:
            continue
        return test_matches[-1].group(0), git_match.group(0)
    return None


def allow():
    sys.stdout.write("{}\n")
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return allow()
    if payload.get("tool_name") not in SHELL_TOOLS:
        return allow()

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or tool_input.get("cmd") or ""
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    if not command:
        return allow()

    hit = verdict(command)
    if hit:
        sys.stdout.write(
            json.dumps(
                {
                    "decision": "block",
                    "reason": MESSAGE.format(test=hit[0], git=hit[1]),
                }
            )
            + "\n"
        )
        return 0
    return allow()


if __name__ == "__main__":
    sys.exit(main())
