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

LEDGER_DIR = Path(
    os.environ.get("CLAIM_GUARD_LEDGER_DIR")
    or Path.home() / ".cache" / "claude-guard-hooks"
)

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


def block(reason, *ledgers):
    cleanup(*ledgers)
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    sid = payload.get("session_id") or "default"
    sid = re.sub(r"[^A-Za-z0-9._-]", "_", str(sid))[:80] or "default"
    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")

    # Second pass (this turn was already blocked once): let it through and
    # clear the ledger. Without this an unfixable claim loops forever.
    if payload.get("stop_hook_active") is True:
        cleanup(verify_ledger, search_ledger)
        return 0

    last = payload.get("last_assistant_message") or ""
    if not last:
        return 0

    if VERIFY_TRIGGERS.search(last) and not has_records(verify_ledger):
        return block(VERIFY_BLOCK, verify_ledger, search_ledger)

    if NEG_TRIGGERS.search(last) and not has_records(search_ledger):
        return block(SEARCH_BLOCK, verify_ledger, search_ledger)

    cleanup(verify_ledger, search_ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
