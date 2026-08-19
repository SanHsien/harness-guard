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

Windows notes:
  - The check command itself runs through the system shell (cmd.exe). For a
    PowerShell one-liner use --cmd "powershell -NoProfile -Command \\"...\\"".
  - Output is decoded as UTF-8 with replacement, so a check tool that prints
    Chinese does not crash the gate on a cp950 console.
"""
import argparse
import json
import os
import re
import subprocess
import sys

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



def allow(args):
    """Codex treats an empty response as an anomaly; every other caller ignores it."""
    if getattr(args, "codex", False):
        sys.stdout.write("{}\n")
    return 0


def main():
    args = parse_args(sys.argv[1:])

    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    is_cursor = bool(payload.get("cursor_version")) or payload.get("hook_event_name") in CURSOR_EVENTS

    # Do not delete this block. It asks "is this stop happening because I
    # already blocked it once this turn?" If so, let it through. Without it, an
    # error that cannot be fixed loops forever: try to end, blocked, try to
    # end, blocked.
    if payload.get("stop_hook_active") is True:
        return allow(args)

    roots = payload.get("workspace_roots") or []
    project_dir = (
        os.environ.get("CLAUDE_PROJECT_DIR")
        or payload.get("cwd")
        or (roots[0] if roots else None)
        or os.getcwd()
    )
    if not os.path.isdir(project_dir):
        return allow(args)

    # A project that opts in overrides whatever the global registration says.
    config = project_config(project_dir)
    lint_cmd = str(config.get("cmd") or args.cmd or "").strip()
    if not lint_cmd:
        return allow(args)

    try:
        proc = subprocess.run(
            lint_cmd,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return allow(args)  # a hanging or missing checker must not trap the turn

    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")

    # A check command that is broken (typo, crash, prints nothing at all)
    # always lets the turn through. A broken checker must never leave someone
    # unable to finish.
    if not out.strip():
        return allow(args)

    pass_pattern = str(config.get("pass") or args.passing or "").strip()
    if pass_pattern and re.search(pass_pattern, out, re.MULTILINE):
        return allow(args)

    fail_pattern = str(config.get("fail") or args.fail or "").strip() or DEFAULT_FAIL
    if re.search(fail_pattern, out, re.MULTILINE):
        failing = [ln for ln in out.splitlines() if re.search(fail_pattern, ln)][:20]
        msg = (
            "Pre-completion check failed (%s). Fix it before ending this turn:\n%s\n"
            % (lint_cmd, "\n".join(failing) or out[:2000])
        )
        if is_cursor:
            # Cursor `stop` cannot veto. Follow up so the agent still sees the failure.
            sys.stdout.write(json.dumps({"followup_message": msg}, ensure_ascii=False))
            return 0
        if args.codex:
            sys.stdout.write(json.dumps({"decision": "block", "reason": msg}, ensure_ascii=False))
            return 0
        sys.stderr.write(msg)
        return 2

    return allow(args)


if __name__ == "__main__":
    sys.exit(main())
