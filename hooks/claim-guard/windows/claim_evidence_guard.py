#!/usr/bin/env python3
"""claim_evidence_guard.py -- Windows-native port of claim-evidence-guard.sh.

Runs when the assistant is about to end the turn, and reconciles the ledger
written by claim_ledger_tracker.py against what was actually said:

  1. Claimed "tested it" / "verification passed" / "confirmed working"
     -> the ledger must contain a real verification command
  2. Claimed "not found" / "does not exist"
     -> the ledger must contain a real search

If the claim and the record do not match, the turn is blocked and the message
says what is missing.

Behaviour matches the shell version exactly, including the fail-open rules:
unreadable input, missing ledger directory, or a second pass through the same
turn all let the turn through. It only intervenes when the claim was made
explicitly AND the ledger has zero matching records.

See claim_ledger_tracker.py for why the Windows port exists at all (short
version: no `jq` on Windows, and a bare `bash` resolves to WSL).

Both hooks in this pair must be installed together.

Adapted from AlethiaQuizForge/no-hallucination (MIT), by way of this repo's
shell version.
"""
import json
import os
import re
import sys
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
    if "/.codex/" in here:
        return Path.home() / ".cache" / "codex-guard-hooks"
    if "/.cursor/" in here:
        return Path.home() / ".cache" / "cursor-guard-hooks"
    return Path.home() / ".cache" / "claude-guard-hooks"


LEDGER_DIR = default_ledger_dir()

VERIFY_TRIGGERS = re.compile(
    r"verified|confirmed|all passing|tests? pass|build passes|all green"
    r"|works now|working now|deployed and verified"
    r"|驗證通過|測試通過|驗證無誤|實測通過|實測有效|全數通過|建置通過|跑通|已驗證|確認無誤"
    r"|所有測試已通過|全部測試通過|編譯成功|建置成功|修改即驗證完成|功能正常|已確認運作正常",
    re.IGNORECASE,
)

NEG_TRIGGERS = re.compile(
    r"doesn't exist|does not exist|not found|no such|couldn't find"
    r"|cannot find|can't find|nothing matching|no evidence|there is no"
    r"|不存在|找不到|沒有找到|查無|沒有任何(相關|紀錄|檔案)|從未出現",
    re.IGNORECASE,
)

VERIFY_BLOCK = (
    "CLAIM-EVIDENCE GUARD: You claimed 'verified / tests pass / confirmed "
    "working', but this session's ledger has no record of any "
    "verification-type command (test, build, status, diff, live run). A "
    "completion claim is a factual claim -- run the verification command "
    "first, then state the result; if it genuinely cannot be verified "
    "automatically, rephrase as 'not yet verified, needs manual "
    "confirmation'."
)

SEARCH_BLOCK = (
    "CLAIM-EVIDENCE GUARD: You asserted something 'does not exist / cannot be "
    "found', but this session's ledger has no record of any search action "
    "(Grep/Glob/find/ls/Select-String). A negative assertion requires an "
    "exhaustive search first -- search, then say it does not exist."
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


def has_records(path):
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def cleanup(*paths):
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


# Cursor's own event names. `hook_event_name` alone does not identify Cursor:
# Claude Code sends it too (capitalised -- "Stop", "PreToolUse"), so treating
# its presence as "this is Cursor" made the Stop guards emit a Cursor
# follow-up instead of blocking, on the platform they mainly protect.
CURSOR_EVENTS = frozenset({
    "beforeShellExecution", "afterShellExecution", "beforeReadFile",
    "afterFileEdit", "beforeSubmitPrompt", "beforeMCPExecution", "stop",
})


def is_cursor(payload):
    if payload.get("cursor_version"):
        return True
    return payload.get("hook_event_name") in CURSOR_EVENTS


def session_id(payload):
    sid = (
        payload.get("session_id")
        or payload.get("conversation_id")
        or payload.get("turn_id")
        or "default"
    )
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(sid))[:80] or "default"


def last_message(payload):
    last = payload.get("last_assistant_message") or payload.get("agent_message") or ""
    if isinstance(last, str) and last.strip():
        return last
    path = payload.get("transcript_path")
    if not path:
        return ""
    try:
        data = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(data) > 512000:
        data = data[-512000:]
    found = ""
    for line in data.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        role = str(obj.get("role") or obj.get("type") or "")
        text = obj.get("content") or obj.get("text") or obj.get("message") or ""
        if isinstance(text, list):
            text = "".join(
                (part.get("text") or "") if isinstance(part, dict) else str(part)
                for part in text
            )
        if role.lower() in ("assistant", "ai", "model") and isinstance(text, str):
            found = text
    return found


def block(payload, reason, *ledgers):
    cleanup(*ledgers)
    if is_cursor(payload):
        # Cursor `stop` cannot veto a finished turn. It can only follow up.
        sys.stdout.write(json.dumps({"followup_message": reason}, ensure_ascii=False))
        return 0
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0


def main():
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    sid = session_id(payload)
    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")

    # Second pass (this turn was already blocked once): let it through and
    # clear the ledger. Without this an unfixable claim loops forever.
    if payload.get("stop_hook_active") is True:
        cleanup(verify_ledger, search_ledger)
        return 0

    last = last_message(payload)
    if not last:
        return 0

    if VERIFY_TRIGGERS.search(last) and not has_records(verify_ledger):
        return block(payload, VERIFY_BLOCK, verify_ledger, search_ledger)

    if NEG_TRIGGERS.search(last) and not has_records(search_ledger):
        return block(payload, SEARCH_BLOCK, verify_ledger, search_ledger)

    cleanup(verify_ledger, search_ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
