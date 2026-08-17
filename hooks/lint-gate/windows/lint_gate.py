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
    args, _unknown = parser.parse_known_args(argv)
    return args


def main():
    args = parse_args(sys.argv[1:])

    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    # Do not delete this block. It asks "is this stop happening because I
    # already blocked it once this turn?" If so, let it through. Without it, an
    # error that cannot be fixed loops forever: try to end, blocked, try to
    # end, blocked.
    if payload.get("stop_hook_active") is True:
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not os.path.isdir(project_dir):
        return 0

    # A project that opts in overrides whatever the global registration says.
    config = project_config(project_dir)
    lint_cmd = str(config.get("cmd") or args.cmd or "").strip()
    if not lint_cmd:
        return 0

    try:
        proc = subprocess.run(
            lint_cmd,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0  # a check tool that hangs or cannot start must not trap the turn

    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")

    # A check command that is broken (typo, crash, prints nothing at all)
    # always lets the turn through. A broken checker must never leave someone
    # unable to finish.
    if not out.strip():
        return 0

    pass_pattern = str(config.get("pass") or args.passing or "").strip()
    if pass_pattern and re.search(pass_pattern, out, re.MULTILINE):
        return 0

    fail_pattern = str(config.get("fail") or args.fail or "").strip() or DEFAULT_FAIL
    if re.search(fail_pattern, out, re.MULTILINE):
        failing = [ln for ln in out.splitlines() if re.search(fail_pattern, ln)][:20]
        sys.stderr.write(
            "Pre-completion check failed (%s). Fix it before ending this turn:\n%s\n"
            % (lint_cmd, "\n".join(failing) or out[:2000])
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
