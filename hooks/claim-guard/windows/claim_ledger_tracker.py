#!/usr/bin/env python3
"""claim_ledger_tracker.py -- Windows-native port of claim-ledger-tracker.sh.

Same job as the shell version: after every tool call, quietly append a line to
a ledger recording which verification commands were actually run, which of
those ran tests or a build (a separate `.test` ledger), which searches were
actually performed, and which files were edited. Its partner,
claim_evidence_guard.py, reads that ledger at the end of the turn; a file edited
after the last verification means that verification no longer covers the code.

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
    if "/.gemini/" in here:
        return Path.home() / ".cache" / "antigravity-guard-hooks"
    return Path.home() / ".cache" / "claude-guard-hooks"


LEDGER_DIR = default_ledger_dir()
SHELL_TOOLS = (
    "Bash",
    "Exec",
    "exec",
    "exec_command",
    "shell",
    "shell_command",
    "run_command",
    "Shell",
    "PowerShell",  # Claude Code's PowerShell tool on Windows
)
# Antigravity's search tools are grep_search, find_by_name and list_dir.
SEARCH_TOOLS = ("Grep", "Glob", "grep_search", "GlobTool", "find_by_name", "list_dir")
# Looking something up on the web is a search too (Codex spells the fetch web_fetch).
WEB_TOOLS = ("WebSearch", "WebFetch", "web_fetch")
# Tools that change a file: Claude Code, Codex (apply_patch), Cursor (Write,
# Delete) and Antigravity (write_to_file and the two replace tools).
EDIT_TOOLS = (
    "Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch", "Delete",
    "write_to_file", "replace_file_content", "multi_replace_file_content",
)
# Driving a real browser checks live state, so it counts as verification.
BROWSER_VERIFY_PREFIX = "mcp__claude-in-chrome__"

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
    r"|python3? (-c|-m)|node -e|cmp -s|diff -r|agent-browser"
    # Windows-native equivalents
    r"|dotnet test|Invoke-Pester|Invoke-ScriptAnalyzer"
    r"|Test-Path|Get-Command|Get-Process|Get-Service"
    r"|py -[0-9]|where\.exe|pwsh -c|powershell .*-Command"
    r")",
    re.IGNORECASE,
)

# Tier one: commands that run tests or a build. VERIFY_CMD above is everything
# that checks something, status queries included (`git status`, `ls`,
# `Test-Path`, `--version`); claim_evidence_guard.py wants one of these, written
# to a separate `.test` ledger, before a claim that tests or a build pass.
# This list never changes what counts as verification: `.verify` is written
# from VERIFY_CMD alone, as before.
#
# Add your own runner without editing this file: set CLAIM_GUARD_TEST_CMD to one
# more regular expression (Python syntax here; the POSIX builds pass it to
# `grep -E`). An expression that does not compile is ignored.
#
# Where a program name can start: line start, after a separator, or after a
# runner such as `npx` or `uv run` (with its options).
_START = (
    r"(?:^|[;&|(]\s*|\b(?:npx|bunx|pnpm\s+exec|uv\s+run|poetry\s+run|pipenv\s+run"
    r"|hatch\s+run|time|exec|call)\s+(?:-\S+\s+)*)"
)


def _prog(names):
    """`names` as a program: a path, an .exe suffix and quotes around it allowed.

    Matches `cargo`, `./gradlew` and `& "$env:USERPROFILE\\.cargo\\bin\\cargo.exe"`.
    """
    return _START + r"[\"'&\s]*(?:[^\s;&|]*[/\\])?(?:" + names + r")(?:\.exe|\.cmd|\.bat)?[\"']?(?=\s|$)"


# A test or quality-gate script by its file name.
_SCRIPT_NAME = (
    r"(?:(?:run[-_]?)?tests?(?:[-_.][\w.-]*)?|[\w.-]*\w[-_.](?:tests?|spec)"
    r"|(?:dev|ci)[-_]?check|check[-_]?all|verify[-_]?install)"
)
_TEST_DIR_SCRIPT = r"tests?[/\\][^\s;&|\"']+"
_INTERPRETER = r"python[\d.]*|py|node|bash|sh|zsh|pwsh|powershell|bun|deno|ruby|perl|php"

TEST_BUILD_PATTERNS = (
    _prog(r"npm|pnpm|yarn|bun") + r"\s+(?:run\s+)?(?:test|build|check|typecheck|e2e)\b",
    _prog(r"deno") + r"\s+(?:test|task)\b",
    _prog(r"cargo") + r"\s+(?:\+\S+\s+)?(?:test|build|check|nextest|clippy)\b",
    _prog(r"go") + r"\s+(?:test|build|vet)\b",
    _prog(r"dotnet") + r"\s+(?:test|build)\b",
    _prog(r"mvnw?|gradlew?") + r"[^|;&\n]*\b(?:test|build|verify|check|package)\b",
    _prog(r"make") + r"(?:\s+-\S+)*\s+(?:test|check|build|all)\b",
    _prog(r"playwright") + r"\s+test\b",
    _prog(r"node") + r"(?:\s+-\S+)*\s+--test\b",
    _prog(r"cmake") + r"\s+--build\b",
    _prog(r"pytest|py\.test|jest|vitest|mocha|tsc|tox|nox|ctest|msbuild|phpunit|rspec"),
    _prog(r"bash|sh|zsh") + r"\s+-n\b",
    # a test script handed to an interpreter: python tests/x.py, pwsh -File dev_check.ps1
    _prog(_INTERPRETER) + r"[^|;&\n]*?(?<![\w.-])(?:" + _SCRIPT_NAME
    + r"\.(?:py|ps1|sh|js|mjs|cjs|ts|bat|cmd)|" + _TEST_DIR_SCRIPT + r"\.(?:py|ps1|sh|js|mjs|cjs|ts))\b",
    # ... or run directly: ./run-tests.sh, & "C:\repo\tests\Run-All.ps1"
    _START + r"[\"'&\s]*(?:[^\s;&|\"']*[/\\])?(?:" + _SCRIPT_NAME
    + r"\.(?:ps1|sh|bat|cmd|py)|" + _TEST_DIR_SCRIPT + r"\.(?:ps1|sh|bat|cmd))\b",
    r"-m\s+(?:pytest|unittest|compileall|py_compile|doctest)\b",
    r"\bpy_compile\b",
    r"(?<![\w-])Invoke-Pester\b",
    # reading a CI run's result: the tests ran there
    r"\bgh\s+(?:run\s+(?:view|watch|list)|pr\s+checks)\b",
)
TEST_CMD = re.compile("|".join("(?:%s)" % p for p in TEST_BUILD_PATTERNS), re.IGNORECASE | re.MULTILINE)


def is_test_command(command, extra=None):
    """True when `command` runs tests or a build (tier one)."""
    if TEST_CMD.search(command):
        return True
    if extra is None:
        extra = os.environ.get("CLAIM_GUARD_TEST_CMD") or ""
    if extra:
        try:
            return re.search(extra, command, re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            return False
    return False


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
        or payload.get("conversationId")  # Antigravity
        or payload.get("turn_id")
        or "default"
    )
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(sid))[:80] or "default"


def is_antigravity(payload):
    """Antigravity names its tool call `toolCall` and its session `conversationId`.

    Neither is a field Claude Code, Codex or Cursor send, so either one is a
    reliable sign of the caller -- unlike a field several of them share.
    """
    return isinstance(payload.get("toolCall"), dict) or "conversationId" in payload


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


def tool_args(payload):
    tool_input = payload.get("tool_input") or (payload.get("toolCall") or {}).get("args") or {}
    return tool_input if isinstance(tool_input, dict) else {}


def edited_path(payload):
    args = tool_args(payload)
    for key in ("file_path", "notebook_path", "path", "TargetFile", "AbsolutePath"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def main():
    # Codex treats an empty response as an anomaly, and Antigravity's
    # PostToolUse contract is "an empty JSON object". This hook only ever
    # records, so its answer is always "allow" -- it just has to say so.
    codex = "--codex" in sys.argv
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        if codex:
            sys.stdout.write("{}\n")
        return 0  # unreadable input is never a reason to get in the way
    if not isinstance(payload, dict):
        payload = {}
    antigravity = is_antigravity(payload)
    codex = codex or antigravity

    tool = extract_tool_name(payload)
    command = extract_command(payload)
    if not tool and command:
        tool = "Shell"
    sid = session_id(payload)

    # Claude Code only runs PostToolUse for a call that succeeded; Antigravity
    # runs it for a failed one too and flags it with `error`. A test run that
    # failed is not evidence that the tests pass, so it is not recorded.
    if antigravity and payload.get("error"):
        sys.stdout.write("{}\n")
        return 0

    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")
    edit_ledger = LEDGER_DIR / (sid + ".edit")
    test_ledger = LEDGER_DIR / (sid + ".test")

    if tool in EDIT_TOOLS:
        append(edit_ledger, ("%s %s" % (tool, edited_path(payload)[:160])).rstrip())
        if codex:
            sys.stdout.write("{}\n")
        return 0

    if tool.startswith(BROWSER_VERIFY_PREFIX):
        append(verify_ledger, tool)
        if codex:
            sys.stdout.write("{}\n")
        return 0

    if tool in WEB_TOOLS:
        args = tool_args(payload)
        target = args.get("query") or args.get("url") or ""
        label = "WebSearch" if tool == "WebSearch" else "WebFetch"
        append(search_ledger, ("%s %s" % (label, str(target)[:120])).rstrip())
        if codex:
            sys.stdout.write("{}\n")
        return 0

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
        if is_test_command(command):
            append(test_ledger, command[:120])
        if SEARCH_CMD.search(command):
            append(search_ledger, command[:120])

    if codex:
        sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
