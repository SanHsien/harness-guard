#!/usr/bin/env python3
"""anti_doom_loop_guard.py -- prevents infinite repetition of identical commands.

PreToolUse hook for Bash and Read tool calls. Detects repetitive command loops
and infinite retries often seen in open-weight or long-context model runs:

  1. Repeated identical Bash commands (e.g. executing the same failing query or build 3+ times).
  2. Repeated identical Read queries on the same file without modifying strategy.

When an identical command is issued 3 consecutive times, the hook blocks the call
(exit 2, message on stderr) to break the dead loop and force the agent to re-evaluate.
Non-repeating or alternating commands are permitted without interruption.

Cross-platform: pure Python standard library, zero external dependencies.
Register on PreToolUse. Exit 0 lets the call proceed, exit 2 blocks and aborts turn.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure UTF-8 output across Windows and POSIX locales
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEFAULT_THRESHOLD = 3
BASH_TOOLS = {"Bash", "bash", "execute_command", "run_command", "PowerShell", "powershell"}
READ_TOOLS = {"Read", "read_file", "view_file"}


def get_threshold() -> int:
    try:
        val = int(os.environ.get("ANTI_DOOM_LOOP_THRESHOLD", DEFAULT_THRESHOLD))
        return val if val > 0 else DEFAULT_THRESHOLD
    except ValueError:
        return DEFAULT_THRESHOLD


def get_state_path(session_id: str | None = None) -> Path:
    explicit = os.environ.get("ANTI_DOOM_LOOP_STATE_FILE")
    if explicit:
        return Path(explicit)
    base = Path(tempfile.gettempdir())
    suffix = session_id if session_id else "global"
    return base / f"harness-guard-doom-loop-{suffix}.json"


def get_log_path() -> Path:
    explicit = os.environ.get("ANTI_DOOM_LOOP_LOG_FILE")
    if explicit:
        return Path(explicit)
    return Path(tempfile.gettempdir()) / "harness-guard-doom-loop-audit.jsonl"


def extract_signature(payload: dict) -> tuple[str | None, str | None]:
    """Extract a canonical operation signature and a human-readable summary.

    Returns (signature, summary) or (None, None) if unmonitored.
    """
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool_name in BASH_TOOLS:
        cmd = tool_input.get("command") or tool_input.get("CommandLine") or ""
        cmd_clean = cmd.strip()
        if not cmd_clean:
            return None, None
        summary = cmd_clean if len(cmd_clean) <= 60 else cmd_clean[:57] + "..."
        return f"bash:{cmd_clean}", summary

    if tool_name in READ_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("Path") or ""
        if not path:
            return None, None
        path_clean = str(Path(path).as_posix()).strip()
        offset = tool_input.get("offset") or tool_input.get("StartLine") or 0
        limit = tool_input.get("limit") or tool_input.get("EndLine") or 0
        sig = f"read:{path_clean}:{offset}:{limit}"
        summary = f"read {path_clean} (lines/offset {offset}-{limit})"
        return sig, summary

    return None, None


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {"last_signature": None, "consecutive_count": 0, "summary": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"last_signature": None, "consecutive_count": 0, "summary": None}


def save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def log_block_event(entry: dict) -> None:
    try:
        log_file = get_log_path()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def decide(payload: dict) -> tuple[bool, str | None]:
    sig, summary = extract_signature(payload)
    if not sig:
        return True, None

    session_id = payload.get("session_id")
    state_file = get_state_path(session_id)
    state = load_state(state_file)
    threshold = get_threshold()

    last_sig = state.get("last_signature")
    count = state.get("consecutive_count", 0)

    if sig == last_sig:
        count += 1
    else:
        last_sig = sig
        count = 1

    state["last_signature"] = last_sig
    state["consecutive_count"] = count
    state["summary"] = summary
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    save_state(state_file, state)

    if count >= threshold:
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session_id": session_id,
            "signature": sig,
            "summary": summary,
            "repeated_count": count,
            "threshold": threshold,
            "action": "blocked",
        }
        log_block_event(event)

        message = (
            f"[Anti-Doom-Loop Guard] Detected repeating command loop (repeated {count} times: '{summary}'). "
            "Execution blocked. Please re-evaluate approach instead of retrying identically."
        )
        return False, message

    return True, None


def main() -> int:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        allowed, message = decide(payload)
    except Exception:  # noqa: BLE001 - Fail-open: guard crash must not prevent tool usage
        return 0

    if allowed:
        return 0

    if message:
        sys.stderr.buffer.write(message.encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
