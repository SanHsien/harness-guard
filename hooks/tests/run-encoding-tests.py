#!/usr/bin/env python3
"""Every hook must survive a non-UTF-8 stdin locale.

Run it with:  python hooks/tests/run-encoding-tests.py

The failure this pins down, observed in service on 2026-08-15: a hook that
reads its payload with `json.load(sys.stdin)` decodes it using whatever
encoding the locale hands the process. On a Traditional Chinese Windows
install that is cp950, and any non-ASCII text in the payload -- a Chinese
assistant message, a Chinese comment in a command, an emoji being written --
kills the read. The hook produces nothing, exits non-zero, and fails open.

Silently, and precisely when the content is not English. A bilingual kit whose
trigger phrases include Chinese would never fire a single one of them.

Each case below sends a payload containing Chinese with PYTHONIOENCODING set
to cp950, and asserts the hook still does its job. Reading bytes and decoding
UTF-8 explicitly is what makes them pass.

Expected result: 6 passed, 0 failed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HOOKS = REPO / "hooks"
ENV = dict(os.environ, PYTHONIOENCODING="cp950")

CHINESE = "測試全數通過，驗證無誤"


def run(hook, payload, args=(), env=None):
    return subprocess.run(
        [sys.executable, str(hook)] + list(args),
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env or ENV,
    )


def case(label, hook, payload, expect, args=(), env=None):
    """expect(proc) -> bool"""
    if not hook.exists():
        print("SKIP %s -- %s not found" % (label, hook.name))
        return 0
    proc = run(hook, payload, args, env)
    ok = expect(proc)
    print("%-4s %s" % ("PASS" if ok else "FAIL", label))
    if not ok:
        print("      exit=%s stdout=%r stderr=%r"
              % (proc.returncode, proc.stdout[:120], proc.stderr[:160]))
    return 0 if ok else 1


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    failures = 0
    ledger = REPO / ".encoding-test-ledger"
    ledger_env = dict(ENV, CLAIM_GUARD_LEDGER_DIR=str(ledger))

    failures += case(
        "test-gate-guard blocks a chained commit despite a Chinese comment",
        HOOKS / "test-gate-guard" / "claude-code" / "test_gate_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": "pytest ; git push  # 中文註解"}},
        lambda p: p.returncode == 2,
    )

    failures += case(
        "danger-zone-guard blocks `rm -rf /` despite a Chinese comment",
        HOOKS / "danger-zone-guard" / "claude-code" / "danger_zone_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /  # 全部刪掉"}},
        lambda p: p.returncode == 2,
    )

    failures += case(
        "no-emoji-guard blocks an emoji next to Chinese text",
        HOOKS / "no-emoji-guard" / "claude-code" / "no-emoji-guard.py",
        {"tool_name": "Write",
         "tool_input": {"file_path": "note.md", "content": "完成了 \U0001F680"}},
        lambda p: p.returncode == 2,
    )

    failures += case(
        "claim-ledger-tracker records a command written in Chinese",
        HOOKS / "claim-guard" / "windows" / "claim_ledger_tracker.py",
        {"session_id": "enc", "tool_name": "Bash",
         "tool_input": {"command": "pytest -q  # 跑測試"}},
        lambda p: (ledger / "enc.verify").exists()
        and (ledger / "enc.verify").stat().st_size > 0,
        env=ledger_env,
    )

    failures += case(
        "claim-evidence-guard reads a Chinese claim and blocks it",
        HOOKS / "claim-guard" / "windows" / "claim_evidence_guard.py",
        {"session_id": "enc-empty", "last_assistant_message": CHINESE},
        lambda p: b'"block"' in p.stdout,
        env=dict(ENV, CLAIM_GUARD_LEDGER_DIR=str(ledger / "empty")),
    )

    failures += case(
        "lint-gate blocks a failing check when the payload holds Chinese",
        HOOKS / "lint-gate" / "windows" / "lint_gate.py",
        {"stop_hook_active": False, "note": CHINESE},
        lambda p: p.returncode == 2,
        args=("--cmd", "%s -c \"print('found 3 errors')\"" % sys.executable,
              "--fail", "[1-9][0-9]* errors?"),
    )

    if ledger.exists():
        for path in sorted(ledger.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        ledger.rmdir()

    print("\nfailures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
