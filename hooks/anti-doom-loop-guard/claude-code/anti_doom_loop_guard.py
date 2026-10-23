#!/usr/bin/env python3
"""anti_doom_loop_guard.py -- prevents infinite repetition of identical commands.

Pre-tool-call hook for shell and file-read calls. Detects repetitive command loops
and infinite retries often seen in open-weight or long-context model runs:

  1. Repeated identical shell commands (e.g. executing the same failing query or build 3+ times).
  2. Repeated identical file reads without modifying strategy.

When an identical call is issued 3 consecutive times, the hook blocks it to break
the dead loop and force the agent to re-evaluate. Non-repeating or alternating
calls are permitted without interruption, and any other tool call in between
(an edit, for instance) resets the count: the agent changed something, so the
next identical command is not a blind retry.

One file, four agents. Hooks are installed as flat files and may not import each
other, so the shared core (signature, state, threshold, audit log) and the thin
per-agent adapters live side by side here. Only the two ends differ -- how a
payload is read, and how "no" is said:

  agent         payload                              block
  ------------  -----------------------------------  ----------------------------------
  claude        tool_name / tool_input               exit 2, reason on stderr
  codex         tool_name / tool_input (Bash,        exit 0, {"decision":"block",
                apply_patch, ...) -- needs --agent   "reason":...} on stdout
                codex, the payload looks like
                Claude's
  cursor        hook_event_name = preToolUse         exit 0, {"permission":"deny",...}
                (Shell/Read/Write/Delete) or         on stdout
                beforeShellExecution / afterFileEdit
  antigravity   toolCall {name, args}                exit 0, {"decision":"deny",...}
                (run_command, view_file, ...)        on stdout

The caller is identified by its own fields or event names, never by one shared
field: Claude Code and Cursor both send `hook_event_name`, but only Cursor spells
it in camelCase. `--agent <claude|codex|cursor|antigravity>` overrides detection.

Cross-platform: pure Python standard library, zero external dependencies.
Fail-open: any error, malformed input or unknown event lets the call proceed.
"""
import json
import os
import re
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
AGENTS = ("claude", "codex", "cursor", "antigravity")

# Tool names per agent. Claude Code and Codex share the payload shape but not
# the vocabulary: Codex runs commands as Bash / exec_command and edits as
# apply_patch (hook input still reports tool_name "apply_patch").
BASH_TOOLS = {"Bash", "bash", "execute_command", "run_command", "PowerShell", "powershell"}
READ_TOOLS = {"Read", "read_file", "view_file"}
CODEX_SHELL_TOOLS = {"Bash", "exec", "shell", "exec_command", "shell_command", "local_shell"}
CURSOR_SHELL_TOOLS = {"Shell"}
CURSOR_READ_TOOLS = {"Read"}
ANTIGRAVITY_SHELL_TOOLS = {"run_command"}
ANTIGRAVITY_READ_TOOLS = {"view_file"}

# Cursor's own event names (all camelCase). Claude Code's are capitalised
# ("PreToolUse"), so a bare `hook_event_name` does not identify either of them.
CURSOR_EVENTS = frozenset({
    "sessionStart", "sessionEnd", "preToolUse", "postToolUse", "postToolUseFailure",
    "subagentStart", "subagentStop", "beforeShellExecution", "afterShellExecution",
    "beforeMCPExecution", "afterMCPExecution", "beforeReadFile", "afterFileEdit",
    "beforeSubmitPrompt", "preCompact", "stop", "afterAgentResponse", "afterAgentThought",
})
# Events where Cursor expects a {"permission": ...} answer.
CURSOR_PERMISSION_EVENTS = frozenset({
    "preToolUse", "beforeShellExecution", "beforeMCPExecution", "beforeReadFile",
})
# Events that mean "the agent did something else". beforeReadFile is not here
# and not counted either: its payload has the path but no offset or limit, so it
# cannot tell paging through a big file from a blind retry. The Read tool on
# preToolUse carries the full tool input and is counted instead.
CURSOR_RESET_EVENTS = frozenset({"afterFileEdit", "beforeMCPExecution"})

PATH_KEYS = ("file_path", "path", "target_file", "AbsolutePath", "Path", "TargetFile")
RANGE_KEYS = ("offset", "limit", "start_line", "end_line", "StartLine", "EndLine")

# Parsed-event kinds
CALL = "call"      # a monitored call: count it
RESET = "reset"    # some other tool call: the count starts over
IGNORE = "ignore"  # not a tool call at all (or an event we do not handle): no change


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
    # A session id ends up in a file name; keep it to characters that are safe
    # on every platform instead of letting a slash fail the write silently.
    suffix = re.sub(r"[^A-Za-z0-9._-]", "_", str(session_id))[:120] if session_id else "global"
    return base / f"harness-guard-doom-loop-{suffix}.json"


def get_log_path() -> Path:
    explicit = os.environ.get("ANTI_DOOM_LOOP_LOG_FILE")
    if explicit:
        return Path(explicit)
    return Path(tempfile.gettempdir()) / "harness-guard-doom-loop-audit.jsonl"


# -- core: signatures, state, decision ---------------------------------------


def _first(mapping: dict, *keys: str):
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def command_event(command) -> tuple:
    """A shell command. An empty one is not worth counting."""
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    cmd_clean = command.strip() if isinstance(command, str) else ""
    if not cmd_clean:
        return RESET, None, None
    summary = cmd_clean if len(cmd_clean) <= 60 else cmd_clean[:57] + "..."
    return CALL, f"bash:{cmd_clean}", summary


def read_event(tool_input: dict) -> tuple:
    """A file read where the agent names path, offset and limit itself (Claude Code)."""
    path = tool_input.get("file_path") or tool_input.get("Path") or ""
    if not path:
        return RESET, None, None
    path_clean = str(Path(path).as_posix()).strip()
    offset = tool_input.get("offset") or tool_input.get("StartLine") or 0
    limit = tool_input.get("limit") or tool_input.get("EndLine") or 0
    sig = f"read:{path_clean}:{offset}:{limit}"
    summary = f"read {path_clean} (lines/offset {offset}-{limit})"
    return CALL, sig, summary


def generic_read_event(args) -> tuple:
    """A file read whose argument names this guard cannot vouch for (Cursor, Antigravity).

    The whole argument object is the signature, so a different range, page or
    any other parameter makes it a different read. Paging through a big file is
    never mistaken for a blind retry because of an argument name guessed wrong.
    """
    if not isinstance(args, dict) or not args:
        return RESET, None, None
    path = _first(args, *PATH_KEYS)
    span = ",".join(f"{key}={args[key]}" for key in RANGE_KEYS if key in args)
    summary = f"read {Path(str(path)).as_posix() if path else '(file)'}" + (f" ({span})" if span else "")
    return CALL, "read:" + _canonical(args), summary


def load_state(path: Path) -> dict:
    empty = {"last_signature": None, "consecutive_count": 0, "summary": None}
    if not path.is_file():
        return empty
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else empty
    except (OSError, ValueError):
        return empty


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


def count_call(agent: str, session_id, sig: str, summary: str) -> tuple[bool, str | None]:
    """The shared core: count consecutive identical calls, block at the threshold."""
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
        log_block_event({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent": agent,
            "session_id": session_id,
            "signature": sig,
            "summary": summary,
            "repeated_count": count,
            "threshold": threshold,
            "action": "blocked",
        })
        message = (
            f"[Anti-Doom-Loop Guard] Detected repeating command loop (repeated {count} times: '{summary}'). "
            "Execution blocked. Please re-evaluate approach instead of retrying identically."
        )
        return False, message

    return True, None


def reset_count(session_id) -> None:
    state_file = get_state_path(session_id)
    if state_file.is_file():
        save_state(state_file, {"last_signature": None, "consecutive_count": 0, "summary": None})


# -- adapters: payload in --------------------------------------------------------


def is_cursor(payload: dict) -> bool:
    if payload.get("cursor_version"):
        return True
    return payload.get("hook_event_name") in CURSOR_EVENTS


def is_antigravity(payload: dict) -> bool:
    return isinstance(payload.get("toolCall"), dict) or "conversationId" in payload


def detect_agent(payload: dict, forced: str | None = None) -> str:
    if forced in AGENTS:
        return forced
    if is_antigravity(payload):
        return "antigravity"
    if is_cursor(payload):
        return "cursor"
    return "claude"


def forced_agent(argv: list[str]) -> str | None:
    """`--agent NAME`, `--agent=NAME`, or the older `--codex` spelling."""
    for index, arg in enumerate(argv):
        if arg == "--codex":
            return "codex"
        if arg == "--agent" and index + 1 < len(argv):
            return argv[index + 1].lower()
        if arg.startswith("--agent="):
            return arg.split("=", 1)[1].lower()
    return None


def session_of(agent: str, payload: dict):
    if agent == "cursor":
        return payload.get("conversation_id") or payload.get("session_id")
    if agent == "antigravity":
        return payload.get("conversationId")
    return payload.get("session_id")


def parse_claude(payload: dict) -> tuple:
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not tool_name:
        return IGNORE, None, None
    if not isinstance(tool_input, dict):
        return RESET, None, None
    if tool_name in BASH_TOOLS:
        return command_event(tool_input.get("command") or tool_input.get("CommandLine") or "")
    if tool_name in READ_TOOLS:
        return read_event(tool_input)
    return RESET, None, None


def parse_codex(payload: dict) -> tuple:
    """Codex has no read tool (it reads through the shell), so only commands count.

    `apply_patch` also carries its patch text in tool_input.command, so the tool
    name has to be checked before the field is trusted.
    """
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not tool_name:
        return IGNORE, None, None
    if tool_name in CODEX_SHELL_TOOLS and isinstance(tool_input, dict):
        return command_event(tool_input.get("command") or tool_input.get("cmd") or "")
    return RESET, None, None


def parse_cursor(payload: dict) -> tuple:
    event = payload.get("hook_event_name") or ""
    if event == "beforeShellExecution":
        return command_event(payload.get("command") or "")
    if event in CURSOR_RESET_EVENTS:
        return RESET, None, None
    if event == "preToolUse":
        tool_name = payload.get("tool_name") or ""
        tool_input = payload.get("tool_input")
        if tool_name in CURSOR_SHELL_TOOLS and isinstance(tool_input, dict):
            return command_event(tool_input.get("command") or tool_input.get("cmd") or "")
        if tool_name in CURSOR_READ_TOOLS:
            return generic_read_event(tool_input)
        return (RESET, None, None) if tool_name else (IGNORE, None, None)
    return IGNORE, None, None


def parse_antigravity(payload: dict) -> tuple:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return IGNORE, None, None  # PreInvocation, Stop, ...: not a tool call
    name = tool_call.get("name") or ""
    args = tool_call.get("args")
    if not name:
        return IGNORE, None, None
    if name in ANTIGRAVITY_SHELL_TOOLS and isinstance(args, dict):
        return command_event(args.get("CommandLine") or args.get("command") or "")
    if name in ANTIGRAVITY_READ_TOOLS:
        return generic_read_event(args)
    return RESET, None, None


PARSERS = {
    "claude": parse_claude,
    "codex": parse_codex,
    "cursor": parse_cursor,
    "antigravity": parse_antigravity,
}


def decide(payload: dict, agent: str | None = None) -> tuple[bool, str | None]:
    agent = agent or detect_agent(payload)
    kind, sig, summary = PARSERS[agent](payload)
    session_id = session_of(agent, payload)

    if kind == IGNORE:
        return True, None
    if kind == RESET:
        reset_count(session_id)
        return True, None
    return count_call(agent, session_id, sig, summary)


# -- adapters: answer out --------------------------------------------------------


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")


def emit_allow(agent: str, payload: dict) -> int:
    """Let the call through, in words the agent understands.

    Antigravity gets {"decision": "ask"}: `decision` is required there (an
    empty `{}` is read as a deny with no reason), and "allow" would approve the
    call automatically, skipping a permission prompt the user still wants.
    """
    if agent == "codex":
        _emit({})
    elif agent == "antigravity":
        _emit({"decision": "ask"})
    elif agent == "cursor":
        if payload.get("hook_event_name") in CURSOR_PERMISSION_EVENTS:
            _emit({"permission": "allow"})
        else:
            _emit({})
    return 0


def emit_deny(agent: str, message: str) -> int:
    if agent == "codex":
        _emit({"decision": "block", "reason": message})
        return 0
    if agent == "cursor":
        _emit({"permission": "deny", "user_message": message, "agent_message": message})
        return 0
    if agent == "antigravity":
        _emit({"decision": "deny", "reason": message})
        return 0
    sys.stderr.buffer.write(message.encode("utf-8"))
    return 2


def main(argv: list[str] | None = None) -> int:
    forced = forced_agent(sys.argv[1:] if argv is None else argv)
    agent = forced if forced in AGENTS else "claude"
    payload: dict = {}
    try:
        raw = sys.stdin.buffer.read()
        loaded = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        payload = loaded if isinstance(loaded, dict) else {}
        agent = detect_agent(payload, forced)
        allowed, message = decide(payload, agent)
    except Exception:  # noqa: BLE001 - Fail-open: guard crash must not prevent tool usage
        try:
            return emit_allow(agent, payload)
        except Exception:  # noqa: BLE001
            return 0

    if allowed or not message:
        return emit_allow(agent, payload)
    return emit_deny(agent, message)


if __name__ == "__main__":
    sys.exit(main())
