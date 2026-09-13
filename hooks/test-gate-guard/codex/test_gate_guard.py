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

# stdout and stderr take the locale codec too. Where that is not UTF-8, a hook
# blocks correctly and then dies with UnicodeEncodeError while printing its own
# message, so the user sees a traceback instead of the reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


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
SHELL_TOOLS = ("Bash", "shell", "exec", "exec_command")

MESSAGE = (
    "TEST GATE: the test command `{test}` and `{git}` are joined with `;` or a "
    "newline, so the commit still runs when the tests come back red -- this is "
    "the exact shape of a real incident. Join them with `&&` instead, or split "
    "them into two calls and check that the first one exited 0 before "
    "committing."
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
        payload = read_payload()
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
