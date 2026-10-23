#!/usr/bin/env python3
"""lint_gate.py -- Windows-native port of lint-gate.sh.

Runs one check command when the assistant is about to end the turn. If the
check fails, the failing lines are handed back and the turn is blocked until
they are fixed.

Three settings. Pass them as arguments -- unlike the `VAR=value command`
prefix the shell version uses, arguments mean the same thing in cmd.exe, in
PowerShell, and in Git Bash, so the same settings.json line works whichever
shell ends up running it:

  --cmd    the check command to run (required; omit it and this does nothing)
  --fail   if this regex matches the output, this run failed
  --pass   if this regex matches, it passed. Omit to mean "passes as long as
           --fail does not match"

Examples, as they would appear in settings.json on Windows:

  python "C:\\Users\\<you>\\.claude\\hooks\\lint_gate.py" --cmd "npm run lint" --fail "[1-9][0-9]* error"
  python "C:\\Users\\<you>\\.claude\\hooks\\lint_gate.py" --cmd "ruff check ." --fail "^Found [1-9]"

The environment variables LINT_CMD / FAIL_PATTERN / PASS_PATTERN still work as
a fallback, so a config carried over from the shell version keeps running.

Per-project config, which is the point of registering this once and forgetting
about it: if the project directory contains `.lint-gate.json`, its settings win
over both. Register the hook globally with no arguments and it does nothing
anywhere -- until a project opts in by dropping this file in its root:

    {
      "cmd": "python -m pytest -q",
      "fail": "[1-9][0-9]* (failed|error)",
      "pass": null
    }

Order of precedence: .lint-gate.json > command-line arguments > environment.
A project that has no such file is never slowed down or blocked.

Antigravity (Stop event, registered by `install.py --agent antigravity`): the
Stop payload has `conversationId`, `workspacePaths` and a `terminationReason`
but no `stop_hook_active`. The project is the first of `workspacePaths`
(CLAUDE_PROJECT_DIR is ignored there), only a normal finish is checked (not a
user cancel or an error), a failing check answers
{"decision":"continue","reason":...} and everything else answers {}. Because
there is no `stop_hook_active`, a failure identical to the one this
conversation was last blocked on is let through the second time -- the same
"block once, then let go" that Claude Code's flag gives -- so an error the
agent cannot fix does not trap the turn. A clean run forgets the failure.

Windows notes:
  - The check command itself runs through the system shell (cmd.exe). For a
    PowerShell one-liner use --cmd "powershell -NoProfile -Command \\"...\\"".
  - Output is decoded as UTF-8 with replacement, so a check tool that prints
    Chinese does not crash the gate on a cp950 console.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

# stdout and stderr take the locale codec too. Where that is not UTF-8, a hook
# blocks correctly and then dies with UnicodeEncodeError while printing its own
# message, so the user sees a traceback instead of the reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


DEFAULT_FAIL = r"[1-9][0-9]* (error|ERROR)"
TIMEOUT_SECONDS = int(os.environ.get("LINT_TIMEOUT", "120"))
PROJECT_CONFIG = ".lint-gate.json"


def project_config(project_dir):
    """Read .lint-gate.json from the project root, if there is one.

    A malformed or unreadable file is ignored rather than fatal: a typo in a
    config file must not leave someone unable to end a turn.
    """
    path = os.path.join(project_dir, PROJECT_CONFIG)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--cmd", default=os.environ.get("LINT_CMD", ""))
    parser.add_argument("--fail", dest="fail", default=os.environ.get("FAIL_PATTERN", ""))
    parser.add_argument("--pass", dest="passing", default=os.environ.get("PASS_PATTERN", ""))
    # Codex reads JSON on stdout and treats silence as an anomaly, so the
    # installer passes this when it registers the Windows build there.
    parser.add_argument("--codex", action="store_true")
    args, _unknown = parser.parse_known_args(argv)
    return args


# Cursor's own event names. `hook_event_name` alone does not identify Cursor:
# Claude Code sends it too (capitalised -- "Stop", "PreToolUse"), so treating
# its presence as "this is Cursor" made the Stop guards emit a Cursor
# follow-up instead of blocking, on the platform they mainly protect.
CURSOR_EVENTS = frozenset({
    "beforeShellExecution", "afterShellExecution", "beforeReadFile",
    "afterFileEdit", "beforeSubmitPrompt", "beforeMCPExecution", "stop",
})



def is_antigravity(payload):
    """Antigravity names its tool call `toolCall` and its session `conversationId`.

    Neither is a field Claude Code, Codex or Cursor send, so either one is a
    reliable sign of the caller -- unlike a field several of them share.
    """
    return isinstance(payload.get("toolCall"), dict) or "conversationId" in payload


# `terminationReason` values that mean "the model finished its turn". The others
# (user cancel, error, invocation or token limits, a hook's own terminate) are
# not a moment to run the checks.
ANTIGRAVITY_NORMAL_STOPS = ("NO_TOOL_CALL", "TERMINAL_STEP_TYPE")


def allow(args, antigravity=False):
    """Codex and Antigravity want a JSON object back; every other caller ignores it."""
    if getattr(args, "codex", False) or antigravity:
        sys.stdout.write("{}\n")
    return 0


def antigravity_state_path(payload):
    base = os.environ.get("HARNESS_GUARD_STATE_DIR") or tempfile.gettempdir()
    sid = re.sub(r"[^A-Za-z0-9._-]", "_", str(payload.get("conversationId") or "default"))[:80]
    return os.path.join(base, "harness-guard-agy-lint-stop-%s.json" % (sid or "default"))


def read_blocked_fingerprint(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data.get("blocked") if isinstance(data, dict) else None


def forget_failure(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def main():
    args = parse_args(sys.argv[1:])

    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    is_cursor = bool(payload.get("cursor_version")) or payload.get("hook_event_name") in CURSOR_EVENTS
    antigravity = is_antigravity(payload)
    state_file = antigravity_state_path(payload) if antigravity else None

    reason_code = payload.get("terminationReason") or ""
    if antigravity and reason_code and reason_code not in ANTIGRAVITY_NORMAL_STOPS:
        return allow(args, antigravity)

    # Do not delete this block. It asks "is this stop happening because I
    # already blocked it once this turn?" If so, let it through. Without it, an
    # error that cannot be fixed loops forever: try to end, blocked, try to
    # end, blocked.
    if payload.get("stop_hook_active") is True:
        return allow(args)

    roots = payload.get("workspace_roots") or []
    if antigravity:
        # Not CLAUDE_PROJECT_DIR: it would be left over from some other tool.
        workspaces = payload.get("workspacePaths")
        roots = workspaces if isinstance(workspaces, list) else []
        project_dir = (roots[0] if roots else None) or os.getcwd()
    else:
        project_dir = (
            os.environ.get("CLAUDE_PROJECT_DIR")
            or payload.get("cwd")
            or (roots[0] if roots else None)
            or os.getcwd()
        )
    if not isinstance(project_dir, str) or not os.path.isdir(project_dir):
        return allow(args, antigravity)

    # A project that opts in overrides whatever the global registration says.
    config = project_config(project_dir)
    lint_cmd = str(config.get("cmd") or args.cmd or "").strip()
    if not lint_cmd:
        return allow(args, antigravity)

    try:
        proc = subprocess.run(
            lint_cmd,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return allow(args, antigravity)  # a hanging or missing checker must not trap the turn

    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")

    # A check command that is broken (typo, crash, prints nothing at all)
    # always lets the turn through. A broken checker must never leave someone
    # unable to finish.
    if not out.strip():
        return allow(args, antigravity)

    pass_pattern = str(config.get("pass") or args.passing or "").strip()
    if pass_pattern and re.search(pass_pattern, out, re.MULTILINE):
        if state_file:
            forget_failure(state_file)
        return allow(args, antigravity)

    fail_pattern = str(config.get("fail") or args.fail or "").strip() or DEFAULT_FAIL
    if re.search(fail_pattern, out, re.MULTILINE):
        failing = [ln for ln in out.splitlines() if re.search(fail_pattern, ln)][:20]
        msg = (
            "Pre-completion check failed (%s). Fix it before ending this turn:\n%s\n"
            % (lint_cmd, "\n".join(failing) or out[:2000])
        )
        if antigravity:
            fingerprint = hashlib.sha256(msg.encode("utf-8", "replace")).hexdigest()[:16]
            if read_blocked_fingerprint(state_file) == fingerprint:
                return allow(args, antigravity)  # the same failure, blocked once already
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as fh:
                    json.dump({"blocked": fingerprint}, fh)
            except OSError:
                pass  # without the note the same failure may block again; still bounded by Antigravity
            sys.stdout.write(json.dumps({"decision": "continue", "reason": msg}, ensure_ascii=False) + "\n")
            return 0
        if is_cursor:
            # Cursor `stop` cannot veto. Follow up so the agent still sees the failure.
            sys.stdout.write(json.dumps({"followup_message": msg}, ensure_ascii=False))
            return 0
        if args.codex:
            sys.stdout.write(json.dumps({"decision": "block", "reason": msg}, ensure_ascii=False))
            return 0
        sys.stderr.write(msg)
        return 2

    if state_file:
        forget_failure(state_file)
    return allow(args, antigravity)


if __name__ == "__main__":
    sys.exit(main())
