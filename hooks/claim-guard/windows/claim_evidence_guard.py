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

  3. Claimed "tests pass" / "the build passes" specifically, and the record
     has only status queries (`git status`, `ls`, `Test-Path`), or an edit
     after the last test or build run
     -> a notice, not a block (see TEST_CLAIM_TRIGGERS for why)

Behaviour matches the shell version exactly, including the fail-open rules:
unreadable input, missing ledger directory, or a second pass through the same
turn all let the turn through. It only intervenes when the claim was made
explicitly AND the ledger has zero matching records.

See claim_ledger_tracker.py for why the Windows port exists at all (short
version: no `jq` on Windows, and a bare `bash` resolves to WSL).

Both hooks in this pair must be installed together.

Subagents (SubagentStop event; Claude Code, and Codex where it fires). A
subagent's tool calls are in a ledger of its own, `<session>.<agent_id>.*`, as
well as in the parent's (see claim_ledger_tracker.py). When the subagent stops,
its report -- the SubagentHandback message if it used that tool, plus its last
message -- is reconciled with that ledger alone, by the same trigger words. A
mismatch is a notice the user sees, never a block: see SUBAGENT_NOTICE for the
measurement. Only the subagent's own ledger is removed here; the parent's is
never read or touched, so the parent's Stop check is exactly what it was.

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
import time
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

# Words that contain "verified" / "confirmed" without claiming it: a negation
# ("not yet verified", "unconfirmed", "never verified") or a code identifier
# (`is_verified`, `verified_at`, `confirmed()`, `--confirmed`, `verified.py`).
# They are removed before matching. Only those exact shapes: "reverified",
# "Built/verified", "Done.Verified", "verified(live box)" are still claims.
# Quoted text is NOT removed: ``Done. All `tests pass`.`` is still a claim, and
# so is 「驗證通過」 -- wrapping a claim in quotes must not get it past the guard.
# The POSIX builds strip the same pattern with jq; keep the two in step.
NOT_A_CLAIM = re.compile(
    r"(?:\bun|\bnot (?:yet )?|n\Wt (?:yet )?|\bnever |\b[A-Za-z0-9]*_|(?<![^\s`(])--)(?:verified|confirmed)"
    r"|(?:verified|confirmed)(?:_|\(\))"
    r"|(?<=[/`])(?:verified|confirmed)(?-i:\.(?:py|js|ts|tsx|md|json|sh|txt|ya?ml|toml|rs|go|java|rb))\b",
    re.IGNORECASE,
)

# Tier two of a verification claim. "Tests pass" / "the build passes" is a
# claim about a test or build run, so beyond the ledger check above it wants a
# record in the `.test` ledger (claim_ledger_tracker.py's TEST_BUILD_PATTERNS)
# made after the last edit. `git status`, `ls`, `Test-Path` are status queries:
# they satisfy "verified / confirmed", not "tests pass".
#
# This tier is a notice the user sees, never a block. Replayed against 40 local
# sessions on 2026-11-21 before it was written, a block would have been wrong
# about half the time: manual checks worded as 測試通過, a result from an
# earlier turn or another agent, an edit in a different repository. The notice
# makes the gap visible without costing a turn; everything the guard blocked
# before, it still blocks.
TEST_CLAIM_TRIGGERS = re.compile(
    r"tests? pass|all passing|build passes|all green"
    r"|測試通過|建置通過|全數通過|所有測試已通過|全部測試通過|編譯成功|建置成功",
    re.IGNORECASE,
)
# A condition, not a result: "once the tests pass", 「測試通過後再推」.
TEST_CLAIM_NOT = re.compile(
    r"\b(?:once|if|until|when|after|before|unless)\s+(?:(?:all|the)\s+)*tests?\s+pass"
    r"|測試通過(?:後|之後|再|才)|(?:等到|等|待|直到)(?:全部)?測試通過",
    re.IGNORECASE,
)

NO_TEST_NOTICE = (
    "CLAIM-EVIDENCE GUARD (notice): you said tests or a build pass, but no test or build "
    "command ran this turn -- only status queries such as git status, ls or Test-Path.\n"
    "  Last verification: %s\n"
    "If the tests ran in an earlier turn or in another agent, say where; otherwise run them "
    "before saying they pass."
)

STALE_TEST_NOTICE = (
    "CLAIM-EVIDENCE GUARD (notice): you said tests or a build pass, but files were edited "
    "after the last test or build run, so it did not cover the current code.\n"
    "  Last test run: %s\n  Later edit: %s"
)


def is_test_claim(text):
    return TEST_CLAIM_TRIGGERS.search(TEST_CLAIM_NOT.sub(" ", text)) is not None


def test_tier_notice(last, verify_ledger, test_ledger, edit_ledger):
    """The notice for a test claim without a current test run, or None."""
    if not is_test_claim(last):
        return None
    if not has_records(test_ledger):
        return NO_TEST_NOTICE % (last_line(verify_ledger) or "(none)")
    if edited_since_verify(test_ledger, edit_ledger):
        return STALE_TEST_NOTICE % (last_line(test_ledger), last_line(edit_ledger))
    return None


# -- subagents -----------------------------------------------------------------
#
# A subagent's report is checked against the subagent's own ledger when it stops.
# Every finding is a notice, never a block. Replayed against 1058 local subagent
# runs on 2026-11-21 before this was written: 26 were flagged (2.5%), and of the
# 17 the parent rules would have blocked none was a real miss -- "confirmed" as a
# review category ("confirmed 3, needs_validation 2"), the review report written
# after the last check, an error message quoted with 找不到 in it, a web lookup
# worded as "verified against the docs". A block would have cost a subagent turn
# each time for nothing; the notice names the missing evidence and leaves the
# judgement to whoever reads the report.
SUBAGENT_NOTICE = "CLAIM-EVIDENCE GUARD (subagent notice): subagent %s "

SUB_NO_VERIFY = (
    "reported 'verified / tests pass / confirmed', but its own ledger has no verification "
    "command (test, build, status, diff, live run).\n"
    "Missing evidence: any verification command run by that subagent. Treat the report as "
    "not yet verified until someone checks it."
)
SUB_STALE = (
    "reported 'verified / tests pass / confirmed', but it edited files after its last verification "
    "command, so that run did not cover what it handed back.\n"
    "  Last verification: %s\n  Later edit: %s\n"
    "Missing evidence: a verification run after that edit."
)
SUB_NO_TEST = (
    "said tests or a build pass, but its own ledger has no test or build command -- only status "
    "queries such as git status, ls or Test-Path.\n"
    "  Last verification: %s\n"
    "Missing evidence: a test or build run by that subagent."
)
SUB_STALE_TEST = (
    "said tests or a build pass, but it edited files after its last test or build run.\n"
    "  Last test run: %s\n  Later edit: %s\n"
    "Missing evidence: a test or build run after that edit."
)
SUB_NO_SEARCH = (
    "asserted something 'does not exist / cannot be found', but its own ledger has no search "
    "(Grep/Glob/find/ls/Select-String/WebSearch).\n"
    "Missing evidence: a search by that subagent."
)

SUBAGENT_LEDGER_KINDS = ("verify", "search", "edit", "test")
# A subagent ledger nobody collected (no SubagentStop registered, or the subagent
# was killed) is removed by its own session once it has been idle this long.
ORPHAN_SECONDS = 24 * 3600
AGENT_LEDGER_TAIL = re.compile(r"[A-Za-z0-9_-]+\.(?:verify|search|edit|test|report)")


def subagent_findings(text, who, verify_ledger, search_ledger, edit_ledger, test_ledger):
    """What `text` claims that the subagent's own ledger does not back, as notices."""
    last = NOT_A_CLAIM.sub(" ", text)
    prefix = SUBAGENT_NOTICE % who
    found = []
    if VERIFY_TRIGGERS.search(last):
        if not has_records(verify_ledger):
            found.append(prefix + SUB_NO_VERIFY)
        elif edited_since_verify(verify_ledger, edit_ledger):
            found.append(prefix + SUB_STALE % (last_line(verify_ledger), last_line(edit_ledger)))
        elif is_test_claim(last):
            if not has_records(test_ledger):
                found.append(prefix + SUB_NO_TEST % (last_line(verify_ledger) or "(none)"))
            elif edited_since_verify(test_ledger, edit_ledger):
                found.append(prefix + SUB_STALE_TEST % (last_line(test_ledger), last_line(edit_ledger)))
    if NEG_TRIGGERS.search(last) and not has_records(search_ledger):
        found.append(prefix + SUB_NO_SEARCH)
    return found


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


def agent_id(payload):
    """The subagent this event is about, or "". Same shape as the tracker's."""
    value = payload.get("agent_id")
    if not isinstance(value, str) or not value.strip():
        return ""
    return re.sub(r"[^A-Za-z0-9_-]", "_", value.strip())[:64]


def is_codex(payload):
    """`turn_id` is a Codex extension; Claude Code does not send it."""
    return isinstance(payload.get("turn_id"), str)


def handback_report(transcript_path):
    """The last SubagentHandback message in a subagent's transcript, or "".

    The shape is the one Claude Code writes: one JSON object per line, an
    assistant line's `message.content` holding `tool_use` blocks. Anything
    else is skipped, so a different format makes this silent, never wrong.
    """
    if not isinstance(transcript_path, str) or not transcript_path:
        return ""
    try:
        with open(os.path.expanduser(transcript_path), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    found = ""
    for line in data.splitlines():
        if "SubagentHandback" not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for part in content:
            if (isinstance(part, dict) and part.get("type") == "tool_use"
                    and part.get("name") == "SubagentHandback" and isinstance(part.get("input"), dict)):
                text = part["input"].get("message")
                if isinstance(text, str) and text.strip():
                    found = text
    return found


def prune_orphan_agent_ledgers(sid):
    """Remove this session's subagent ledgers that no SubagentStop collected."""
    try:
        now = time.time()
        for path in LEDGER_DIR.iterdir():
            name = path.name
            if (name.startswith(sid + ".") and AGENT_LEDGER_TAIL.fullmatch(name[len(sid) + 1:])
                    and now - path.stat().st_mtime > ORPHAN_SECONDS):
                path.unlink()
    except OSError:
        pass


def subagent_stop(payload):
    """SubagentStop: check the subagent's report against its own ledger. Never blocks.

    The parent session's ledger is not read and not removed here.
    """
    codex = is_codex(payload)

    def done(notices=()):
        if notices:
            show_notices(payload, list(notices))
        elif codex:
            sys.stdout.write("{}\n")  # Codex wants JSON from SubagentStop
        return 0

    aid = agent_id(payload)
    if not aid:
        return done()
    sid = session_id(payload)
    stem = sid + "." + aid
    ledgers = {kind: LEDGER_DIR / (stem + "." + kind) for kind in SUBAGENT_LEDGER_KINDS}
    report = LEDGER_DIR / (stem + ".report")
    try:
        # Claude Code also fires SubagentStop for its own internal agents (prompt
        # suggestions, /btw); in a session without --agent those have no type.
        if payload.get("agent_type") == "" or payload.get("stop_hook_active") is True:
            return done()
        tracked = any(path.exists() for path in ledgers.values())
        if codex and not tracked:
            # Codex's documented PostToolUse fields do not promise agent_id. With
            # no ledger at all, "ran nothing" and "was never told" look the same.
            return done()
        try:
            handed_back = report.read_text(encoding="utf-8", errors="replace")
        except OSError:
            handed_back = ""
        if not handed_back.strip():
            handed_back = handback_report(payload.get("agent_transcript_path"))
        last = payload.get("last_assistant_message")
        text = "\n".join(part for part in (handed_back, last) if isinstance(part, str) and part.strip())
        if not text:
            return done()
        who = "%s (%s)" % (payload.get("agent_type") or "unnamed", aid)
        return done(subagent_findings(
            text, who, ledgers["verify"], ledgers["search"], ledgers["edit"], ledgers["test"]))
    finally:
        cleanup(report, *ledgers.values())
        prune_orphan_agent_ledgers(sid)


def block(payload, reason, *ledgers):
    cleanup(*ledgers)
    if is_cursor(payload):
        # Cursor `stop` cannot veto a finished turn. It can only follow up.
        sys.stdout.write(json.dumps({"followup_message": reason}, ensure_ascii=False))
        return 0
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    return 0


CODEX_TEST_COMMAND = re.compile(
    r"(?i)(?:pwsh(?:\.exe)? (?:-NoProfile )?-File [\w./\\-]*\bdev_check\.ps1"
    r"|python(?:\.exe)? (?:-B )?[\w./-]*tests?/run-tests\.py)"
)
CODEX_ROLLOUT_TAIL_BYTES = 4 * 1024 * 1024


def codex_transcript_test(payload, edit_ledger):
    """Recover a successful, standalone check from native current-turn events."""
    sid, turn = payload.get("session_id"), payload.get("turn_id")
    path = payload.get("transcript_path")
    if not all(isinstance(value, str) and value for value in (sid, turn, path)):
        return False
    if payload.get("hook_event_name") != "Stop":
        return False

    # Require the turn start inside the bounded window. In particular, do not
    # mistake a prior turn's successful run or text printed by a tool for evidence.
    started = False
    last_command_ms = None
    try:
        with Path(path).open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            if size > CODEX_ROLLOUT_TAIL_BYTES:
                stream.seek(size - CODEX_ROLLOUT_TAIL_BYTES)
                stream.readline(CODEX_ROLLOUT_TAIL_BYTES)
            else:
                stream.seek(0)
            lines = stream.read(CODEX_ROLLOUT_TAIL_BYTES).splitlines()
    except (OSError, ValueError):
        return False

    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "event_msg":
            continue
        data = event.get("payload")
        if not isinstance(data, dict):
            continue
        if data.get("type") == "task_started":
            started = data.get("turn_id") == turn
            last_command_ms = None
            continue
        if (not started or data.get("type") != "item_completed"
                or data.get("thread_id") != sid or data.get("turn_id") != turn):
            continue
        item = data.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "FileChange":
            last_command_ms = None
        if item.get("type") != "CommandExecution":
            continue
        # An intervening shell command could have edited files or failed a
        # rerun. Recover only when the last native command is a successful check.
        last_command_ms = None
        argv = item.get("command")
        milliseconds = data.get("completed_at_ms")
        if (isinstance(argv, list) and len(argv) == 3
                and all(isinstance(arg, str) for arg in argv)
                and Path(argv[0].replace("\\", "/")).name.lower() == "pwsh.exe"
                and argv[1].lower() == "-command" and CODEX_TEST_COMMAND.fullmatch(argv[2].strip())
                and item.get("source") == "unified_exec_startup"
                and item.get("status") == "completed" and type(item.get("exit_code")) is int
                and item["exit_code"] == 0 and type(milliseconds) is int):
            last_command_ms = milliseconds

    edit_ns = mtime_ns(edit_ledger)
    return last_command_ms is not None and (
        edit_ns is None or last_command_ms * 1_000_000 >= edit_ns
    )


def evaluate(payload, last, second_pass, verify_ledger, search_ledger, edit_ledger=None,
             notices=None, test_ledger=None):
    """Reconcile the last message with the ledger. Returns a block reason, or None.

    Ledgers are cleaned up here, in both outcomes, exactly where the checks
    decide. `second_pass` means "this message was already blocked once":
    Claude Code says so with `stop_hook_active`, Antigravity has to be told by
    the caller. When the turn is let through, a test-tier notice (if any) is
    appended to `notices` for the caller to show; a block reason replaces it.
    """
    if edit_ledger is None:
        edit_ledger = verify_ledger.with_suffix(".edit")
    if test_ledger is None:
        test_ledger = verify_ledger.with_suffix(".test")
    ledgers = (verify_ledger, search_ledger, edit_ledger, test_ledger)
    last = NOT_A_CLAIM.sub(" ", last)
    notice = None
    if VERIFY_TRIGGERS.search(last):
        recovered_test = (
            not second_pass and not has_records(verify_ledger)
            and codex_transcript_test(payload, edit_ledger)
        )
        if not has_records(verify_ledger) and not second_pass and not recovered_test:
            cleanup(*ledgers)
            return VERIFY_BLOCK
        if not second_pass and not recovered_test and edited_since_verify(verify_ledger, edit_ledger):
            reason = STALE_BLOCK % (last_line(verify_ledger), last_line(edit_ledger))
            cleanup(*ledgers)
            return reason
        repo_root = target_repo_root(payload)
        quality_err = check_quality_summary_gate(repo_root)
        if quality_err:
            cleanup(*ledgers)
            return quality_err
        if not recovered_test:
            notice = test_tier_notice(last, verify_ledger, test_ledger, edit_ledger)

    def allow():
        cleanup(*ledgers)
        if notice and notices is not None:
            notices.append(notice)
        return None

    # A second pass may relax only the session-ledger requirement. Machine
    # evidence remains fail-closed until the claim is revised or Full is rerun.
    if second_pass:
        return allow()

    if NEG_TRIGGERS.search(last) and not has_records(search_ledger):
        cleanup(*ledgers)
        return SEARCH_BLOCK

    return allow()


def show_notices(payload, notices):
    """Show allow-path notices the way this agent can without blocking.

    Claude Code and Codex print a Stop `systemMessage` to the user. Cursor's
    only Stop output is a follow-up, which would start another turn, and
    Antigravity's allow must be `{}` exactly, so for those two the notice goes
    to stderr only.
    """
    if not notices:
        return
    text = "\n\n".join(notices)
    sys.stderr.write(text + "\n")
    if is_cursor(payload) or is_antigravity(payload):
        return
    sys.stdout.write(json.dumps({"systemMessage": text}, ensure_ascii=False))


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
    notices = []
    reason = evaluate(
        payload, last, second_pass, LEDGER_DIR / (sid + ".verify"), LEDGER_DIR / (sid + ".search"),
        notices=notices,
    )
    if not reason:
        try:
            state.unlink()
        except OSError:
            pass
        show_notices(payload, notices)  # stderr only: the allow below must stay {}
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

    # A subagent finishing is not the session finishing: it gets its own check
    # and must never reach the code below, which empties the session's ledger.
    if payload.get("hook_event_name") == "SubagentStop":
        return subagent_stop(payload)

    sid = session_id(payload)
    prune_orphan_agent_ledgers(sid)
    verify_ledger = LEDGER_DIR / (sid + ".verify")
    search_ledger = LEDGER_DIR / (sid + ".search")

    last = last_message(payload)
    if not last:
        return 0

    notices = []
    reason = evaluate(
        payload, last, payload.get("stop_hook_active") is True, verify_ledger, search_ledger,
        notices=notices,
    )
    if reason:
        # evaluate() already cleaned the ledgers, as block() used to.
        return block(payload, reason)
    show_notices(payload, notices)
    return 0


if __name__ == "__main__":
    sys.exit(main())
