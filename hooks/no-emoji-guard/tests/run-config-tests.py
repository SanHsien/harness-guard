#!/usr/bin/env python3
"""no-emoji-guard settings must survive a reinstall.

    python hooks/no-emoji-guard/tests/run-config-tests.py

Editing EXEMPT_PATH_SUBSTRINGS inside the script works until someone re-runs
the installer, which copies the file over the top and takes the setting with
it. That happened here on 2026-08-15: a reinstall turned the hook back on for
someone who had deliberately switched it off, and nothing said so.

The settings therefore also live in `no-emoji-guard.json` beside the installed
script, which no installer writes. This suite pins the four behaviours that
make that trustworthy.

Expected: 10 passed, 0 failed (five cases against each build).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent
BUILDS = [
    ("claude-code", HOOKS / "claude-code" / "no-emoji-guard.py"),
    ("codex", HOOKS / "codex" / "no-emoji-guard.py"),
]

EMOJI = "ship it \U0001F680"


def run(hook, config, path="note.md", tool_name="Write"):
    """Run the hook with a given config file content (None = no file)."""
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        if config is not None:
            config_path = Path(tmp) / "no-emoji-guard.json"
            config_path.write_text(config, encoding="utf-8")
            env["NO_EMOJI_GUARD_CONFIG"] = str(config_path)
        else:
            env["NO_EMOJI_GUARD_CONFIG"] = str(Path(tmp) / "absent.json")

        payload = json.dumps(
            {
                "tool_name": tool_name,
                "tool_input": {"file_path": path, "content": EMOJI},
            }
        ).encode("utf-8")
        proc = subprocess.run(
            [sys.executable, str(hook)], input=payload, capture_output=True, env=env
        )
    return proc.returncode == 2


CASES = [
    ("no config file: blocks", None, "note.md", True),
    ('"enabled": false: allows', '{"enabled": false}', "note.md", False),
    (
        "exempt path matches: allows",
        '{"exempt_path_substrings": ["/vault/"]}',
        "/home/me/vault/note.md",
        False,
    ),
    (
        "exempt path does not match: blocks",
        '{"exempt_path_substrings": ["/vault/"]}',
        "/home/me/work/note.md",
        True,
    ),
    # A broken config must fail towards protection, not away from it.
    ("malformed config: still blocks", "{ this is not json", "note.md", True),
]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    failures = 0
    for build, hook in BUILDS:
        if not hook.exists():
            print("SKIP %s -- not found" % build)
            continue
        print("-- %s build" % build)
        for label, config, path, must_block in CASES:
            blocked = run(hook, config, path)
            ok = blocked == must_block
            failures += not ok
            print(
                "%-4s %-40s expected=%s got=%s"
                % (
                    "PASS" if ok else "FAIL",
                    label,
                    "block" if must_block else "allow",
                    "block" if blocked else "allow",
                )
            )
        print()

    print("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
