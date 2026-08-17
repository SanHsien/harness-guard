#!/usr/bin/env python3
"""verify-install.py -- proves the hooks and skills are installed, instead of assuming it.

This kit exists because a claim with no evidence behind it is worthless. Its
own installation is not exempt. Every one of these hooks has a silent failure
mode: register it wrong, or leave out a dependency, and nothing errors -- the
hook simply never runs, and you believe you are protected when you are not.

So this script does not read the config and pronounce it fine. It test-fires
each installed hook with a synthetic payload and checks what actually comes
back.

Run it after installing, and again after any change to settings.json:

    python scripts/verify-install.py

Exit code 0 means every installed piece answered correctly. Exit code 1 means
at least one thing is broken, and the line above says which.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
GEMINI_DIR = Path.home() / ".gemini"
SETTINGS = CLAUDE_DIR / "settings.json"
HOOKS_DIR = CLAUDE_DIR / "hooks"

JQ_DEPENDENT = re.compile(r"claim-(evidence-guard|ledger-tracker)|lint-gate\.sh")
SCRATCH = Path(tempfile.mkdtemp(prefix="harness-verify-"))

results = []


def record(ok, label, detail=""):
    results.append((ok, label, detail))
    status = "PASS" if ok else "FAIL"
    print("%-4s %s%s" % (status, label, (" -- " + detail) if detail else ""))


def note(label, detail=""):
    print("     %s%s" % (label, (" -- " + detail) if detail else ""))


def section(title):
    print("\n== %s ==" % title)


def find_hook(*names):
    for name in names:
        path = HOOKS_DIR / name
        if path.exists():
            return path
    return None


def run_hook(path, payload, env=None, timeout=60, args=()):
    """Feed a hook one synthetic payload and return the finished process."""
    full_env = dict(os.environ)
    full_env["CLAIM_GUARD_LEDGER_DIR"] = str(SCRATCH / "ledger")
    if env:
        full_env.update(env)

    if path.suffix == ".py":
        cmd = [sys.executable, str(path)]
    elif path.suffix in (".sh", ""):
        bash = shutil.which("bash")
        if IS_WINDOWS:
            git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
            bash = str(git_bash) if git_bash.exists() else bash
        if not bash:
            return None
        cmd = [bash, str(path)]
    else:
        return None

    cmd = cmd + [str(a) for a in args]

    try:
        return subprocess.run(
            cmd,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=full_env,
            cwd=str(SCRATCH),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        note("could not run %s" % path.name, str(exc))
        return None


# -- environment -----------------------------------------------------------


def check_environment():
    section("Environment")
    note("os", "%s %s" % (platform.system(), platform.release()))
    note("python", "%s (%s)" % (platform.python_version(), sys.executable))

    jq = shutil.which("jq")
    if jq:
        note("jq", jq)
    else:
        note("jq", "not installed")

    if IS_WINDOWS:
        found = []
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / "bash.exe"
            if candidate.exists() and str(candidate) not in found:
                found.append(str(candidate))
        if found:
            note("bash on PATH", " | ".join(found[:3]))
            if "system32" in found[0].lower():
                note(
                    "warning",
                    "the first bash on PATH is WSL. A hook registered as "
                    "`bash ~/.claude/hooks/x.sh` will not find the file.",
                )
    return jq


# -- settings.json ---------------------------------------------------------


def collect_commands(hooks_block):
    for _event, entries in (hooks_block or {}).items():
        for entry in entries or []:
            for hook in entry.get("hooks", []) or []:
                command = hook.get("command")
                if isinstance(command, str):
                    yield command


def check_settings(jq_present):
    section("settings.json (Claude Code)")
    if not SETTINGS.exists():
        note("settings.json", "does not exist yet at %s (skipped)" % SETTINGS)
        return []

    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, ValueError) as exc:
        record(False, "settings.json is valid JSON", str(exc))
        return []
    except UnicodeDecodeError as exc:
        record(False, "settings.json is UTF-8", str(exc))
        return []
    record(True, "settings.json is valid JSON", str(SETTINGS))

    commands = list(collect_commands(data.get("hooks")))
    record(bool(commands), "at least one hook is registered", "%d found" % len(commands))

    for command in commands:
        if IS_WINDOWS and re.match(r"^\s*bash\s", command):
            record(
                False,
                "no bare `bash` in a Windows hook command",
                command[:70] + " -- resolves to WSL; use full Git Bash path or Python build",
            )
        if jq_present is None and JQ_DEPENDENT.search(command):
            record(
                False,
                "a jq-dependent hook is registered but jq is missing",
                command[:70] + " -- it will exit quietly and protect nothing",
            )

        match = re.search(r"([A-Za-z]:[\\/][^\"']+|~[\\/][^\s\"']+|[\\/][^\s\"']+)\.(sh|py)", command)
        if match:
            raw = match.group(0)
            path = Path(os.path.expanduser(raw.replace("\\", "/")))
            if not path.exists():
                record(False, "hook file referenced by settings exists", raw)
    return commands


# -- Antigravity environment -----------------------------------------------


def check_antigravity():
    section("Google Antigravity (AGY)")
    skills_dir = GEMINI_DIR / "config" / "skills"
    if skills_dir.exists():
        installed = [p.name for p in skills_dir.iterdir() if p.is_dir()]
        record(True, "Antigravity global skills directory", "%d skills installed (%s)" % (len(installed), ", ".join(installed[:4])))
    else:
        note("Antigravity skills", "not yet populated under %s" % skills_dir)


# -- live fire -------------------------------------------------------------


def switched_off(hook, probe_path):
    """Is this copy of no-emoji-guard deliberately not guarding this path?

    Being switched off is a legitimate state -- installed, registered, and
    allowing everything -- so reporting it as a failure would be a false alarm.
    Three ways to end up there, in the order the hook itself resolves them.
    Returns a reason string, or None if the guard should be blocking.
    """
    config_path = hook.parent / "no-emoji-guard.json"
    try:
        with open(config_path, encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        config = {}
    if not isinstance(config, dict):
        config = {}

    if config.get("enabled") is False:
        return '"enabled": false in %s' % config_path

    exempt = config.get("exempt_path_substrings")
    if isinstance(exempt, list) and any(
        isinstance(s, str) and s and s in probe_path for s in exempt
    ):
        return "the probe path is exempt via %s" % config_path

    try:
        text = hook.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^EXEMPT_PATH_SUBSTRINGS\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    entries = re.findall(r"""["']((?:\\.|[^"'\\])*)["']""", match.group(1))
    if any(entry and entry.encode().decode("unicode_escape") in probe_path
           for entry in entries):
        return "EXEMPT_PATH_SUBSTRINGS in the script exempts the probe path"
    return None


def check_no_emoji_guard():
    hook = find_hook("no-emoji-guard.py")
    if not hook:
        note("no-emoji-guard", "not installed, skipped")
        return
    probe = str(SCRATCH / "a.md")
    reason = switched_off(hook, probe)
    if reason:
        note(
            "no-emoji-guard",
            "installed and loaded, but switched off (%s), so it allows writes. "
            "That is a setting, not a fault -- reverse it there to switch the "
            "guard on." % reason,
        )
        return
    blocked = run_hook(
        hook,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(SCRATCH / "a.md"), "content": "ship it \U0001F680"},
        },
    )
    allowed = run_hook(
        hook,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(SCRATCH / "a.md"), "content": "ship it"},
        },
    )
    if not blocked or not allowed:
        record(False, "no-emoji-guard runs")
        return
    record(blocked.returncode == 2, "no-emoji-guard blocks a write containing emoji")
    record(allowed.returncode == 0, "no-emoji-guard allows a clean write")


def check_claim_guard():
    tracker = find_hook("claim_ledger_tracker.py", "claim-ledger-tracker.sh")
    guard = find_hook("claim_evidence_guard.py", "claim-evidence-guard.sh")
    if not tracker and not guard:
        note("claim-guard", "not installed, skipped")
        return
    record(
        bool(tracker and guard),
        "claim-guard is installed as a pair",
        "installing only one silently disables the feature",
    )
    if not (tracker and guard):
        return

    empty = run_hook(
        guard,
        {
            "session_id": "verify-empty",
            "last_assistant_message": "I ran the tests, all passing.",
        },
    )
    if not empty:
        record(False, "claim-evidence-guard runs")
        return
    record(
        '"block"' in (empty.stdout or ""),
        "claim-guard blocks 'tests pass' with an empty ledger",
    )

    logged = run_hook(
        tracker,
        {
            "session_id": "verify-logged",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
        },
    )
    after = run_hook(
        guard,
        {
            "session_id": "verify-logged",
            "last_assistant_message": "I ran the tests, all passing.",
        },
    )
    if logged is None or after is None:
        record(False, "claim-ledger-tracker runs")
        return
    record(
        '"block"' not in (after.stdout or ""),
        "claim-guard allows the same claim once the ledger has a test run",
    )


def check_lint_gate():
    hook = find_hook("lint_gate.py", "lint-gate.sh")
    if not hook:
        note("lint-gate", "not installed, skipped")
        return
    fake_check = "%s -c \"print('found 3 errors')\"" % sys.executable
    env = {"LINT_CMD": fake_check, "FAIL_PATTERN": "[1-9][0-9]* errors?"}
    args = ("--cmd", fake_check, "--fail", "[1-9][0-9]* errors?")

    failing = run_hook(hook, {"stop_hook_active": False}, env=env, args=args)
    loop = run_hook(hook, {"stop_hook_active": True}, env=env, args=args)

    if hook.suffix == ".py":
        inert = run_hook(hook, {"stop_hook_active": False})
        config = SCRATCH / ".lint-gate.json"
        config.write_text(
            json.dumps({"cmd": fake_check, "fail": "[1-9][0-9]* errors?"}),
            encoding="utf-8",
        )
        opted_in = run_hook(hook, {"stop_hook_active": False})
        config.unlink()
        if inert and opted_in:
            record(
                inert.returncode == 0,
                "lint-gate does nothing in a project with no .lint-gate.json",
            )
            record(
                opted_in.returncode == 2,
                "lint-gate blocks once a project opts in with .lint-gate.json",
            )
    if not failing or not loop:
        record(False, "lint-gate runs")
        return
    record(failing.returncode == 2, "lint-gate blocks when the check command fails")
    record(
        loop.returncode == 0,
        "lint-gate lets a second pass through (no infinite block loop)",
    )


def check_test_gate():
    hook = find_hook("test_gate_guard.py", "test-gate-guard.py")
    if not hook:
        note("test-gate-guard", "not installed, skipped")
        return
    chained = run_hook(
        hook, {"tool_name": "Bash", "tool_input": {"command": "pytest ; git push"}}
    )
    gated = run_hook(
        hook, {"tool_name": "Bash", "tool_input": {"command": "pytest && git push"}}
    )
    if not chained or not gated:
        record(False, "test-gate-guard runs")
        return
    record(chained.returncode == 2, "test-gate-guard blocks `pytest ; git push`")
    record(gated.returncode == 0, "test-gate-guard allows `pytest && git push`")


def check_danger_zone_guard():
    hook = find_hook("danger_zone_guard.py", "danger-zone-guard.py")
    if not hook:
        note("danger-zone-guard", "not installed, skipped")
        return
    destructive = run_hook(
        hook, {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
    )
    safe = run_hook(
        hook, {"tool_name": "Bash", "tool_input": {"command": "rm -rf dist/"}}
    )
    if not destructive or not safe:
        record(False, "danger-zone-guard runs")
        return
    record(destructive.returncode == 2, "danger-zone-guard blocks catastrophic `rm -rf /`")
    record(safe.returncode == 0, "danger-zone-guard allows safe `rm -rf dist/`")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="all", choices=["claude", "antigravity", "all"])
    _args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("Verifying the harness installation...")
    jq = check_environment()
    check_settings(jq)
    check_antigravity()

    section("Live fire (each installed hook is run with a synthetic payload)")
    check_no_emoji_guard()
    check_claim_guard()
    check_lint_gate()
    check_test_gate()
    check_danger_zone_guard()

    failed = [r for r in results if not r[0]]
    section("Result")
    print("%d checked, %d failed" % (len(results), len(failed)))
    if failed:
        for _ok, label, detail in failed:
            print("  - %s%s" % (label, (" -- " + detail) if detail else ""))
        print(
            "\nA failure here means that piece is not protecting you, whatever "
            "the config file says."
        )
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
