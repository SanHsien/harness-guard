#!/usr/bin/env python3
"""claim_ledger_tracker.py -- Windows-native port of claim-ledger-tracker.sh.

Same job as the shell version: after every tool call, quietly append a line to
a ledger recording which verification commands were actually run and which
searches were actually performed. Its partner, claim_evidence_guard.py, reads
that ledger at the end of the turn.

Why a separate port instead of running the .sh file:

  1. The shell version needs `jq`. `jq` is not present on a stock Windows box,
     and the shell version's `|| exit 0` means a missing `jq` makes the hook
     silently do nothing. You would think you were protected and you would not
     be -- the exact failure this kit exists to catch.
  2. On Windows, a hook command that starts with a bare `bash` resolves to
     `C:\\Windows\\System32\\bash.exe`, which is WSL, not Git Bash. Inside WSL
     `$HOME` is the Linux home, so `~/.claude/hooks/...` does not exist and the
     script never runs.

This file needs only the Python standard library. Both hooks in this pair must
be installed together -- install one alone and the feature silently stops
working.

Ledger location: %USERPROFILE%\\.cache\\claude-guard-hooks, the same path the
shell version uses, so the two are interchangeable and can even coexist.
Override with the CLAIM_GUARD_LEDGER_DIR environment variable.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

# stdout and stderr take the locale codec too. Where that is not UTF-8, a hook
# blocks correctly and then dies with UnicodeEncodeError while printing its own
# message, so the user sees a traceback instead of the reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def default_ledger_dir():
    env = os.environ.get("CLAIM_GUARD_LEDGER_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().as_posix().lower()
    if "/.codex/" in here or here.endswith("/.codex/hooks/claim_ledger_tracker.py"):
        return Path.home() / ".cache" / "codex-guard-hooks"
    if "/.cursor/" in here:
        return Path.home() / ".cache" / "cursor-guard-hooks"
    return Path.home() / ".cache" / "claude-guard-hooks"


LEDGER_DIR = default_ledger_dir()
SHELL_TOOLS = ("Bash", "Exec", "exec", "shell", "run_command", "Shell")
SEARCH_TOOLS = ("Grep", "Glob", "grep_search", "GlobTool")

# Verification-type commands: tests, builds, status and health checks, diffs,
# live runs. The first group is carried over from the shell version unchanged;
# the second group is what the same intent looks like on Windows.
VERIFY_CMD = re.compile(
    r"(--version"
    r"|npm (run build|test|run check)|yarn (build|test)|pnpm (run build|test)|bun (test|run build)|deno (test|task)"
    r"|pytest|jest|vitest|playwright|cargo test|go test|make (test|check)|uv run"
    r"|py_compile|bash -n|jq (-e |\.)|curl.*-[sI]"
    r"|git\s+(-C\s+\S+\s+)?(status|diff|log)"
    r"|systemctl (status|is-active)"
    r"|test -[fedrwx]|grep -[qcl]|wc -[lcw]"
    r"|python3? (-c|-m)|node -e|cmp -s|diff -r"
    # Windows-native equivalents
    r"|dotnet test|Invoke-Pester|Invoke-ScriptAnalyzer"
    r"|Test-Path|Get-Command|Get-Process|Get-Service"
    r"|py -[0-9]|where\.exe|pwsh -c|powershell .*-Command"
    r")",
    re.IGNORECASE,
)

# Search-type commands: looking for files or looking for text inside them.
SEARCH_CMD = re.compile(
    r"(^|[|;&\s])"
    r"(grep|rg|find|ls|fd|gh api|mdfind|grep_search|code_search"
    r"|Select-String|Get-ChildItem|gci|dir|findstr)"
    r"(\s|$)",
    re.IGNORECASE,
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


def append(path, line):
    """Append one ledger line and force it to disk before returning.

    The flush and fsync are not decoration. A PostToolUse hook is a short-lived
    process the harness can reap as soon as the tool result is ready, and a
    buffered write that has not reached the file system dies with it. Observed
    in service on 2026-08-15: ledger files created at the right moment, with
    the right name, containing zero bytes -- which reads downstream as "no
    evidence" and makes claim-evidence-guard block a claim that was in fact
    backed by a real test run. An empty ledger is worse than no ledger.
    """
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("%s %s\n" % (time.strftime("%H:%M:%S"), line))
        fh.flush()
        os.fsync(fh.fileno())


def session_id(payload):
    sid = (
        payload.get("session_id")
        or payload.get("conversation_id")
        or payload.get("turn_id")
        or "default"
    )
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(sid))[:80] or "default"


def extract_tool_name(payload):
    event = payload.get("hook_event_name") or ""
    if event in ("beforeShellExecution", "afterShellExecution"):
        return "Shell"
    return payload.get("tool_name") or (payload.get("toolCall") or {}).get("name") or ""


def extract_command(payload):
    event = payload.get("hook_event_name") or ""
    if event in ("beforeShellExecution", "afterShellExecution"):
        return payload.get("command") or ""
    tool_input = payload.get("tool_input") or (payload.get("toolCall") or {}).get("args") or {}
    if isinstance(tool_input, str):
        return tool_input
    if not isinstance(tool_input, dict):
        return payload.get("command") or ""
    return (
        tool_input.get("command")
        or tool_input.get("CommandLine")
        or tool_input.get("cmd")
        or payload.get("command")
        or ""
    )


def main():
    # Codex treats an empty response as an anomaly. This hook only ever
    # records, so its answer is always "allow" -- it just has to say so.
    codex = "--codex" in sys.argv
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        if codex:
            sys.stdout.write("{}\n")
        return 0  # unreadable input is never a reason to get in the way

    tool = extract_tool_name(payload)
    command = extract_command(payload)
    if not tool and command:
        tool = "Shell"
    sid = session_id(payload)

    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")

    if tool in SEARCH_TOOLS:
        append(search_ledger, tool)
        if codex:
            sys.stdout.write("{}\n")
        return 0

    if tool in SHELL_TOOLS:
        if not command:
            if codex:
                sys.stdout.write("{}\n")
            return 0
        if VERIFY_CMD.search(command):
            append(verify_ledger, command[:120])
        if SEARCH_CMD.search(command):
            append(search_ledger, command[:120])

    if codex:
        sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
