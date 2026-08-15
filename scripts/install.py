#!/usr/bin/env python3
"""install.py -- one command that reproduces this setup on another machine.

    python scripts/install.py --dry-run              # show exactly what would change
    python scripts/install.py                        # hooks only
    python scripts/install.py --hooks all --skills all   # the full setup
    python scripts/install.py --skills explain,polite

What it does:

  1. Works out the platform and picks the right build of each hook. On Windows
     that means the Python builds -- the shell builds need `jq`, and without
     `jq` they exit 0, which means "allow."
  2. Copies the hook scripts flat into ~/.claude/hooks/.
  3. Merges the matching registrations into ~/.claude/settings.json. Merge, not
     overwrite: existing hooks are kept, and re-running does not duplicate
     anything.
  4. Backs up settings.json before touching it, writes atomically, and reads
     the file back to confirm it is still valid JSON.
  5. Tells you to restart, then points at verify-install.py, which proves the
     hooks actually fire.

  6. With --skills, copies skill folders into ~/.claude/skills/. An existing
     folder of the same name is left alone unless you pass --force, because
     checkpoint and neat-freak are meant to be tuned per person and yours are
     worth more than the stock copies.

What it deliberately does not do: install the rules-file template (that gets
merged into an existing CLAUDE.md by hand, section by section -- see
AGENTS.md), or configure lint-gate (it needs a check command that only you
know).
"""
import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"

# Each entry: which file to copy for this platform, and how to register it.
# `event`/`matcher` follow the Claude Code hooks schema.
HOOKS = {
    "claim-guard": [
        {
            "source": {
                "windows": "hooks/claim-guard/windows/claim_ledger_tracker.py",
                "posix": "hooks/claim-guard/claude-code/claim-ledger-tracker.sh",
            },
            "event": "PostToolUse",
            "matcher": "Bash|Grep|Glob",
            "timeout": 10,
        },
        {
            "source": {
                "windows": "hooks/claim-guard/windows/claim_evidence_guard.py",
                "posix": "hooks/claim-guard/claude-code/claim-evidence-guard.sh",
            },
            "event": "Stop",
            "matcher": None,
            "timeout": 15,
        },
    ],
    "test-gate-guard": [
        {
            "source": {
                "windows": "hooks/test-gate-guard/claude-code/test_gate_guard.py",
                "posix": "hooks/test-gate-guard/claude-code/test_gate_guard.py",
            },
            "event": "PreToolUse",
            "matcher": "Bash",
            "timeout": 10,
        },
    ],
    "no-emoji-guard": [
        {
            "source": {
                "windows": "hooks/no-emoji-guard/claude-code/no-emoji-guard.py",
                "posix": "hooks/no-emoji-guard/claude-code/no-emoji-guard.py",
            },
            "event": "PreToolUse",
            "matcher": "Write|Edit|MultiEdit",
            "timeout": 10,
            "statusMessage": "Scanning for emoji...",
        },
    ],
}

DEFAULT_HOOKS = "claim-guard,test-gate-guard"


def build_command(installed_path):
    """The settings.json command line for a hook that now lives at this path."""
    quoted = '"%s"' % installed_path
    if installed_path.suffix == ".py":
        interpreter = "python" if IS_WINDOWS else "python3"
        return "%s %s" % (interpreter, quoted)
    if IS_WINDOWS:
        # Never a bare `bash` here: on Windows that is System32\bash.exe, i.e.
        # WSL, where this path does not exist and the hook silently never runs.
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            return '"%s" %s' % (git_bash, quoted)
    return quoted


def load_settings(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def already_registered(settings, event, command):
    for entry in (settings.get("hooks", {}).get(event) or []):
        for hook in entry.get("hooks", []) or []:
            if hook.get("command") == command:
                return True
    return False


def register(settings, spec, command):
    """Add one hook to the settings tree, reusing a matching matcher group."""
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault(spec["event"], [])

    definition = {"type": "command", "command": command}
    if spec.get("timeout"):
        definition["timeout"] = spec["timeout"]
    if spec.get("statusMessage"):
        definition["statusMessage"] = spec["statusMessage"]

    for entry in entries:
        if entry.get("matcher") == spec["matcher"] or (
            spec["matcher"] is None and "matcher" not in entry
        ):
            entry.setdefault("hooks", []).append(definition)
            return

    new_entry = {"hooks": [definition]}
    if spec["matcher"]:
        new_entry["matcher"] = spec["matcher"]
    entries.append(new_entry)


def select_skills(requested):
    """Resolve the --skills argument to a list of source folders."""
    available = sorted(p for p in (REPO / "skills").iterdir() if p.is_dir())
    if requested in ("", "none"):
        return []
    if requested == "all":
        return available
    wanted = {name.strip() for name in requested.split(",") if name.strip()}
    by_name = {p.name: p for p in available}
    missing = wanted - set(by_name)
    if missing:
        print("Unknown skill(s): %s" % ", ".join(sorted(missing)))
        print("Available: %s" % ", ".join(by_name))
        return None
    return [by_name[name] for name in sorted(wanted)]


def install_skills(args, claude_dir):
    sources = select_skills(args.skills)
    if not sources:
        return 0 if sources is not None else 2

    skills_dir = claude_dir / "skills"
    print("\nskills -> %s" % skills_dir)
    copied = 0
    for source in sources:
        target = skills_dir / source.name
        if target.exists() and not args.force:
            print("  %-16s already there, left alone (--force to overwrite)" % source.name)
            continue
        if args.dry_run:
            print("  %-16s would copy" % source.name)
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        copied += 1
        print("  %-16s copied" % source.name)

    if copied and not args.dry_run:
        print("  note: checkpoint and neat-freak only produce accurate numbers "
              "once their reference tables match how you file things.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hooks",
        default=DEFAULT_HOOKS,
        help="comma-separated: %s, or `all` (default: %s)"
        % (", ".join(HOOKS), DEFAULT_HOOKS),
    )
    parser.add_argument(
        "--skills",
        default="none",
        help="comma-separated skill folder names, `all`, or `none` (default: none)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite a skill folder that already exists (default: leave it alone)",
    )
    parser.add_argument(
        "--claude-dir",
        default=os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    claude_dir = Path(args.claude_dir)
    hooks_dir = claude_dir / "hooks"
    settings_path = claude_dir / "settings.json"
    key = "windows" if IS_WINDOWS else "posix"

    selected = list(HOOKS) if args.hooks == "all" else [
        name.strip() for name in args.hooks.split(",") if name.strip()
    ]
    unknown = [name for name in selected if name not in HOOKS]
    if unknown:
        print("Unknown hook(s): %s" % ", ".join(unknown))
        print("Available: %s" % ", ".join(HOOKS))
        return 2

    print("platform : %s" % platform.system())
    print("target   : %s" % claude_dir)
    print("hooks    : %s" % ", ".join(selected))
    if args.dry_run:
        print("mode     : dry run, nothing will be written")
    print()

    try:
        settings = load_settings(settings_path)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print("settings.json could not be read: %s" % exc)
        print("Fix that first -- this script will not overwrite a file it cannot parse.")
        return 1

    if IS_WINDOWS and shutil.which("jq") is None:
        print("note: jq is not installed. The Python builds are being used, "
              "which do not need it.\n")

    planned = []
    for name in selected:
        for spec in HOOKS[name]:
            source = REPO / spec["source"][key]
            if not source.exists():
                print("SKIP %s -- missing %s" % (name, source))
                continue
            target = hooks_dir / source.name
            command = build_command(target)
            state = "already registered" if already_registered(
                settings, spec["event"], command
            ) else "will register"
            print("%-16s %-12s %s" % (name, spec["event"], command))
            print("%-16s %-12s %s" % ("", "", state))
            planned.append((spec, source, target, command, state))

    if args.dry_run:
        rc = install_skills(args, claude_dir)
        if rc:
            return rc
        print("\nDry run only. Re-run without --dry-run to apply.")
        return 0

    # 1. copy the scripts
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for _spec, source, target, _command, _state in planned:
        shutil.copyfile(source, target)
        if not IS_WINDOWS:
            os.chmod(target, 0o755)
    print("\ncopied %d file(s) into %s" % (len(planned), hooks_dir))

    # 2. back up settings.json before changing it
    if settings_path.exists():
        backup_dir = claude_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / ("settings.json.bak-%s" % time.strftime("%Y%m%d-%H%M%S"))
        shutil.copyfile(settings_path, backup)
        print("backed up settings.json to %s" % backup)

    # 3. merge the registrations
    added = 0
    for spec, _source, _target, command, state in planned:
        if state == "already registered":
            continue
        register(settings, spec, command)
        added += 1

    if added:
        # Write to a temporary file and move it into place, so a crash halfway
        # through cannot leave a half-written settings.json behind.
        tmp = settings_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, settings_path)

        # 4. read it back -- a broken settings.json stops Claude Code starting
        try:
            load_settings(settings_path)
        except (json.JSONDecodeError, ValueError) as exc:
            print("settings.json is no longer valid JSON: %s" % exc)
            print("Restore from the backup above.")
            return 1
        print("registered %d hook(s); settings.json re-read and still valid" % added)
    else:
        print("nothing new to register")

    rc = install_skills(args, claude_dir)
    if rc:
        return rc

    print("\nNext, in this order:")
    print("  1. Quit Claude Code completely and reopen it. Hooks load at startup.")
    print("  2. Run: python scripts/verify-install.py")
    print("     Exit code 0 means each hook actually fired and answered correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
