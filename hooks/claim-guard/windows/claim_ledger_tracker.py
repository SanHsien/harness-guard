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

LEDGER_DIR = Path(
    os.environ.get("CLAIM_GUARD_LEDGER_DIR")
    or Path.home() / ".cache" / "claude-guard-hooks"
)

# Verification-type commands: tests, builds, status and health checks, diffs,
# live runs. The first group is carried over from the shell version unchanged;
# the second group is what the same intent looks like on Windows.
VERIFY_CMD = re.compile(
    r"(--version"
    r"|npm (run build|test)|pytest|jest|vitest|cargo test|go test|make test|uv run"
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
    r"(^|[|;&]\s*)"
    r"(grep|rg|find|ls|fd|gh api|mdfind"
    r"|Select-String|Get-ChildItem|gci|dir|findstr)"
    r"(\s|$)",
    re.IGNORECASE,
)


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


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0  # unreadable input is never a reason to get in the way

    tool = payload.get("tool_name") or ""
    sid = payload.get("session_id") or "default"
    # A session id becomes part of a filename, so refuse anything that could
    # walk out of the ledger directory.
    sid = re.sub(r"[^A-Za-z0-9._-]", "_", str(sid))[:80] or "default"

    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")

    if tool in ("Grep", "Glob"):
        append(search_ledger, tool)
        return 0

    if tool == "Bash":
        cmd = (payload.get("tool_input") or {}).get("command") or ""
        if not cmd:
            return 0
        if VERIFY_CMD.search(cmd):
            append(verify_ledger, cmd[:120])
        if SEARCH_CMD.search(cmd):
            append(search_ledger, cmd[:120])

    return 0


if __name__ == "__main__":
    sys.exit(main())
