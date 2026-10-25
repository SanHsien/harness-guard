#!/usr/bin/env python3
"""claim_evidence_guard.py -- Windows-native port of claim-evidence-guard.sh.

Runs when the assistant is about to end the turn, and reconciles the ledger
written by claim_ledger_tracker.py against what was actually said:

  1. Claimed "tested it" / "verification passed" / "confirmed working"
     -> the ledger must contain a real verification command, and no file may
        have been edited after the last one (it would not cover the current code)
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

Antigravity (Stop event). Its Stop payload names the conversation and a
`transcriptPath`, but carries no assistant message, so the last model message
is read from the transcript file. The official hooks reference does not
describe that file's line format; the reader here follows the step shape the
`run-workflow` reference documents (`type` PLANNER_RESPONSE with `text`) and
fails open -- no readable model message, no block -- so a different format
makes the guard silent, never wrong. Antigravity's Stop has no
`stop_hook_active`, so "blocked once already" is remembered per conversation by
a fingerprint of the message: the same message a second time is let through.
Block = stdout {"decision":"continue","reason":...}; allow = {}.

Adapted from AlethiaQuizForge/no-hallucination (MIT), by way of this repo's
shell version.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
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
    if "/.gemini/" in here:
        return Path.home() / ".cache" / "antigravity-guard-hooks"
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

STALE_BLOCK = (
    "CLAIM-EVIDENCE GUARD (stale verification): you claimed verified / tests "
    "pass, but files were edited after the last verification command, so it "
    "did not cover the current code.\n  Last verification: %s\n  Later edit: %s\n"
    "Re-run the verification before claiming it; if this change needs no test "
    "(docs, comments), say edited, not re-verified."
)

# Quoted text is a mention, not a claim: 「驗證通過」 or `tests pass` names the
# phrase rather than asserting it.
QUOTED = re.compile(r"「[^」]*」|`[^`]*`")

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


def mtime_ns(path):
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def last_line(path):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return lines[-1] if lines else ""


def edited_since_verify(verify_ledger, edit_ledger):
    """True when the last file edit came after the last verification command.

    Each ledger's mtime is when its last line was appended, so the comparison
    is between the latest edit and the latest verification.
    """
    if not has_records(edit_ledger):
        return False
    edit, verify = mtime_ns(edit_ledger), mtime_ns(verify_ledger)
    return edit is not None and verify is not None and edit > verify


def cleanup(*paths):
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


def target_repo_root(payload):
    workspaces = payload.get("workspacePaths")  # Antigravity
    cwd = (
        payload.get("cwd")
        or payload.get("working_directory")
        or (workspaces[0] if isinstance(workspaces, list) and workspaces else None)
        or os.getcwd()
    )
    path = Path(cwd).resolve()
    for cur in [path, *path.parents]:
        if (cur / "loop-policy.toml").exists() or (cur / ".git").exists():
            return cur
    return path


def check_quality_summary_gate(repo_root: Path) -> str | None:
    policy_file = repo_root / "loop-policy.toml"
    summary_file = repo_root / "artifacts" / "quality-summary.json"
    if not policy_file.exists():
        return None

    try:
        policy = tomllib.loads(policy_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return f"CLAIM-EVIDENCE GUARD: 'loop-policy.toml' is unreadable: {exc}"
    verification = policy.get("verification", {})
    if not isinstance(verification, dict) or verification.get("require_machine_evidence") is not True:
        return None

    if not summary_file.exists():
        return (
            "CLAIM-EVIDENCE GUARD: Target repository defines a quality gate (loop-policy.toml), "
            "but 'artifacts/quality-summary.json' does not exist. Run verification (e.g. dev_check.ps1) "
            "to produce the machine-readable summary before claiming completion."
        )

    try:
        data = json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"CLAIM-EVIDENCE GUARD: 'artifacts/quality-summary.json' is unreadable: {exc}"
    if not isinstance(data, dict):
        return "CLAIM-EVIDENCE GUARD: Quality summary must be a JSON object."

    if data.get("schema_version") != 1:
        return "CLAIM-EVIDENCE GUARD: Quality summary schema_version must be 1."
    if data.get("profile") != "full":
        return "CLAIM-EVIDENCE GUARD: Quality summary profile must be 'full'; Quick evidence cannot prove completion."
    gates = data.get("gates")
    if not isinstance(gates, dict) or not gates:
        return "CLAIM-EVIDENCE GUARD: Quality summary gates must be a non-empty object."
    if any(not isinstance(value, bool) for value in gates.values()):
        return "CLAIM-EVIDENCE GUARD: Every quality summary gate must be boolean."
    if data.get("passed") is not True:
        failed_gates = [key for key, value in gates.items() if not value]
        gates_str = ", ".join(failed_gates) if failed_gates else "unknown"
        return (
            f"CLAIM-EVIDENCE GUARD: Quality summary indicates gate failure (passed=False, failed: {gates_str}). "
            "Resolve failing gates before claiming completion."
        )
    if not all(gates.values()):
        failed_gates = [key for key, value in gates.items() if not value]
        return f"CLAIM-EVIDENCE GUARD: Quality summary has failed gates: {', '.join(failed_gates)}."

    summary_commit = data.get("commit")
    if not isinstance(summary_commit, str) or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", summary_commit) is None:
        return "CLAIM-EVIDENCE GUARD: Quality summary commit must be a full Git object id."
    try:
        head_proc = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "CLAIM-EVIDENCE GUARD: Current git HEAD could not be resolved."
    head_sha = head_proc.stdout.strip()
    if head_proc.returncode != 0 or not head_sha:
        return "CLAIM-EVIDENCE GUARD: Current git HEAD could not be resolved."
    if head_sha.lower() != summary_commit.lower():
        return (
            f"CLAIM-EVIDENCE GUARD: Quality summary commit ({summary_commit[:8]}) does not match "
            f"current git HEAD ({head_sha[:8]}). Re-run Full verification to refresh quality evidence."
        )

    return None


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


def is_antigravity(payload):
    """Antigravity names its tool call `toolCall` and its session `conversationId`.

    Neither is a field Claude Code, Codex or Cursor send, so either one is a
    reliable sign of the caller -- unlike a field several of them share.
    """
    return isinstance(payload.get("toolCall"), dict) or "conversationId" in payload


def session_id(payload):
    sid = (
        payload.get("session_id")
        or payload.get("conversation_id")
        or payload.get("conversationId")  # Antigravity
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


def evaluate(payload, last, second_pass, verify_ledger, search_ledger, edit_ledger=None):
    """Reconcile the last message with the ledger. Returns a block reason, or None.

    Ledgers are cleaned up here, in both outcomes, exactly where the checks
    decide. `second_pass` means "this message was already blocked once":
    Claude Code says so with `stop_hook_active`, Antigravity has to be told by
    the caller.
    """
    if edit_ledger is None:
        edit_ledger = verify_ledger.with_suffix(".edit")
    ledgers = (verify_ledger, search_ledger, edit_ledger)
    last = QUOTED.sub("", last)
    if VERIFY_TRIGGERS.search(last):
        if not has_records(verify_ledger) and not second_pass:
            cleanup(*ledgers)
            return VERIFY_BLOCK
        if not second_pass and edited_since_verify(verify_ledger, edit_ledger):
            reason = STALE_BLOCK % (last_line(verify_ledger), last_line(edit_ledger))
            cleanup(*ledgers)
            return reason
        repo_root = target_repo_root(payload)
        quality_err = check_quality_summary_gate(repo_root)
        if quality_err:
            cleanup(*ledgers)
            return quality_err

    # A second pass may relax only the session-ledger requirement. Machine
    # evidence remains fail-closed until the claim is revised or Full is rerun.
    if second_pass:
        cleanup(*ledgers)
        return None

    if NEG_TRIGGERS.search(last) and not has_records(search_ledger):
        cleanup(*ledgers)
        return SEARCH_BLOCK

    cleanup(*ledgers)
    return None


# -- Antigravity ---------------------------------------------------------------

# `terminationReason` values that mean "the model finished its turn". The others
# (user cancel, error, invocation or token limits, a hook's own terminate) are
# not a completion claim, so there is nothing to check.
ANTIGRAVITY_NORMAL_STOPS = ("NO_TOOL_CALL", "TERMINAL_STEP_TYPE")
TRANSCRIPT_TAIL_BYTES = 512000


def antigravity_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            (part.get("text") or "") if isinstance(part, dict) else str(part)
            for part in value
        )
    return ""


def antigravity_last_message(payload):
    """The last model message in the transcript Antigravity points at, or "".

    One JSON object per line. A line counts as a model message when its step
    type is PLANNER_RESPONSE (optionally with the CORTEX_STEP_TYPE_ prefix) or
    its role is assistant / model / ai. Anything unreadable is skipped.
    """
    path = payload.get("transcriptPath")
    if not isinstance(path, str) or not path:
        return ""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            data = fh.read().decode("utf-8", errors="replace")
        if size > TRANSCRIPT_TAIL_BYTES:
            data = data.split("\n", 1)[-1]  # the first line is cut in the middle
    except OSError:
        return ""
    found = ""
    for line in data.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("type") or obj.get("stepType") or "").upper()
        kind = kind.replace("CORTEX_STEP_TYPE_", "")
        role = str(obj.get("role") or "").lower()
        if kind != "PLANNER_RESPONSE" and role not in ("assistant", "model", "ai"):
            continue
        text = ""
        for key in ("text", "content", "message", "response"):
            text = antigravity_text(obj.get(key))
            if text.strip():
                break
        if not text.strip():
            for key in ("plannerResponse", "planner_response"):
                inner = obj.get(key)
                if isinstance(inner, dict):
                    for sub in ("text", "response", "content", "message"):
                        text = antigravity_text(inner.get(sub))
                        if text.strip():
                            break
                if text.strip():
                    break
        if text.strip():
            found = text
    return found


def state_path(sid):
    base = os.environ.get("HARNESS_GUARD_STATE_DIR") or tempfile.gettempdir()
    return Path(base) / ("harness-guard-agy-claim-stop-%s.json" % sid)


def read_blocked_fingerprint(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("blocked") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def antigravity_stop(payload):
    """Antigravity's Stop: block with {"decision":"continue"}, allow with {}."""
    def allow():
        sys.stdout.write("{}\n")
        return 0

    reason_code = payload.get("terminationReason") or ""
    if reason_code and reason_code not in ANTIGRAVITY_NORMAL_STOPS:
        return allow()

    sid = session_id(payload)
    last = antigravity_last_message(payload)
    if not last:
        return allow()

    fingerprint = hashlib.sha256(last.encode("utf-8", "replace")).hexdigest()[:16]
    state = state_path(sid)
    second_pass = read_blocked_fingerprint(state) == fingerprint
    reason = evaluate(
        payload, last, second_pass, LEDGER_DIR / (sid + ".verify"), LEDGER_DIR / (sid + ".search")
    )
    if not reason:
        try:
            state.unlink()
        except OSError:
            pass
        return allow()
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"blocked": fingerprint}), encoding="utf-8")
    except OSError:
        pass  # without the note the same message may be blocked again; still bounded by Antigravity
    sys.stdout.write(json.dumps({"decision": "continue", "reason": reason}, ensure_ascii=False) + "\n")
    return 0


def main():
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    if is_antigravity(payload):
        return antigravity_stop(payload)

    sid = session_id(payload)
    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")

    last = last_message(payload)
    if not last:
        return 0

    reason = evaluate(
        payload, last, payload.get("stop_hook_active") is True, verify_ledger, search_ledger
    )
    if reason:
        # evaluate() already cleaned the ledgers, as block() used to.
        return block(payload, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
