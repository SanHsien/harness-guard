#!/usr/bin/env python3
"""install.py -- one command that reproduces this setup on another machine.

    python scripts/install.py --dry-run                           # show exactly what would change
    python scripts/install.py                                     # default hooks
    python scripts/install.py --hooks all --skills all            # full setup for Claude Code
    python scripts/install.py --agent antigravity --skills all    # install for Google Antigravity
    python scripts/install.py --agent cursor --hooks all --skills all
    python scripts/install.py --agent codex --hooks all --skills all
    python scripts/install.py --agent all --hooks all --skills all

What it does:

  1. Works out the platform and automated target (Claude Code, Antigravity,
     Cursor, or Codex). Claude Code gets the platform-appropriate hook build.
     On Windows that means Python builds where required -- the shell builds
     need `jq`, and without `jq` they exit 0, which means "allow."
  2. Copies Claude Code hook scripts flat into its hook directory.
  3. Merges Claude Code registrations into ~/.claude/settings.json.
     Merge, not overwrite: existing hooks are kept, and re-running does not duplicate.
  4. Backs up Claude Code settings before touching them, writes atomically, and validates JSON.
  5. With --skills, copies skill folders into the selected agent's skills directory.
     Existing folders of the same name are left alone unless you pass --force.
  6. `--agent cursor` writes ~/.cursor/hooks.json in Cursor's flat format and
     copies Python hooks to ~/.cursor/hooks/. `--agent codex` merges into
     ~/.codex/hooks.json with absolute interpreter paths and installs user
     skills into the shared ~/.agents/skills location Codex documents.
  7. `--agent all` is Claude Code + Antigravity + Cursor + Codex.
"""
import argparse
import json
import os
import platform
import shutil
import stat
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"

# Hook definitions for Claude Code and Windows/POSIX platforms
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
    "danger-zone-guard": [
        {
            # Pure Python, so one file serves every platform. There is no
            # separate windows/ build to get out of sync -- and a shim that
            # imports a sibling folder cannot work here anyway, because hooks
            # are installed flat.
            "source": {
                "windows": "hooks/danger-zone-guard/claude-code/danger_zone_guard.py",
                "posix": "hooks/danger-zone-guard/claude-code/danger_zone_guard.py",
            },
            "event": "PreToolUse",
            "matcher": "Bash",
            "timeout": 10,
        },
    ],
    "lint-gate": [
        {
            "source": {
                "windows": "hooks/lint-gate/windows/lint_gate.py",
                "posix": "hooks/lint-gate/claude-code/lint-gate.sh",
            },
            "event": "Stop",
            "matcher": None,
            "timeout": 60,
            "statusMessage": "Running end-of-session checks...",
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

DEFAULT_HOOKS = "claim-guard,test-gate-guard,danger-zone-guard"

# Cursor uses a flat hooks.json (version + event -> [{command}]), not the
# Claude Code nested matcher groups. Event names are also different, and
# `stop` cannot veto -- the Python hooks already degrade to follow-up there.
CURSOR_HOOKS = {
    "claim-guard": [
        {
            "source": "hooks/claim-guard/windows/claim_ledger_tracker.py",
            "event": "postToolUse",
            "timeout": 10,
        },
        {
            "source": "hooks/claim-guard/windows/claim_evidence_guard.py",
            "event": "stop",
            "timeout": 15,
        },
    ],
    "test-gate-guard": [
        {
            "source": "hooks/test-gate-guard/claude-code/test_gate_guard.py",
            "event": "beforeShellExecution",
            "timeout": 10,
        },
    ],
    "danger-zone-guard": [
        {
            "source": "hooks/danger-zone-guard/claude-code/danger_zone_guard.py",
            "event": "beforeShellExecution",
            "timeout": 10,
        },
    ],
    "lint-gate": [
        {
            "source": "hooks/lint-gate/windows/lint_gate.py",
            "event": "stop",
            "timeout": 60,
        },
    ],
    "no-emoji-guard": [
        {
            "source": "hooks/no-emoji-guard/claude-code/no-emoji-guard.py",
            "event": "preToolUse",
            "matcher": "Write",
            "timeout": 10,
        },
    ],
}

CODEX_HOOKS = {
    "claim-guard": [
        {
            "source": {
                "windows": "hooks/claim-guard/windows/claim_ledger_tracker.py",
                "posix": "hooks/claim-guard/codex/claim-ledger-tracker.sh",
            },
            # The Windows build is the Claude-protocol one; --codex makes it
            # answer in Codex's JSON instead. The posix build is already a
            # Codex build and needs no flag.
            "args_windows": ("--codex",),
            "event": "PostToolUse",
            "matcher": "Bash|Grep|Glob|exec|shell",
            "timeout": 10,
        },
        {
            "source": {
                "windows": "hooks/claim-guard/windows/claim_evidence_guard.py",
                "posix": "hooks/claim-guard/codex/claim-evidence-guard.sh",
            },
            "event": "Stop",
            "matcher": None,
            "timeout": 15,
        },
    ],
    "test-gate-guard": [
        {
            "source": {
                "windows": "hooks/test-gate-guard/codex/test_gate_guard.py",
                "posix": "hooks/test-gate-guard/codex/test_gate_guard.py",
            },
            "event": "PreToolUse",
            "matcher": "exec|shell|exec_command|Bash",
            "timeout": 10,
        },
    ],
    "danger-zone-guard": [
        {
            "source": {
                "windows": "hooks/danger-zone-guard/codex/danger_zone_guard.py",
                "posix": "hooks/danger-zone-guard/codex/danger_zone_guard.py",
            },
            "event": "PreToolUse",
            "matcher": "exec|shell|exec_command|Bash",
            "timeout": 10,
        },
    ],
    "lint-gate": [
        {
            "source": {
                "windows": "hooks/lint-gate/windows/lint_gate.py",
                "posix": "hooks/lint-gate/codex/lint-gate.sh",
            },
            "args_windows": ("--codex",),
            "event": "Stop",
            "matcher": None,
            "timeout": 60,
        },
    ],
    "no-emoji-guard": [
        {
            "source": {
                "windows": "hooks/no-emoji-guard/codex/no-emoji-guard.py",
                "posix": "hooks/no-emoji-guard/codex/no-emoji-guard.py",
            },
            "event": "PreToolUse",
            "matcher": "apply_patch|Write|Edit|MultiEdit",
            "timeout": 10,
        },
    ],
}


def build_command(installed_path, extra_args=()):
    """The command line for an installed hook script."""
    quoted = '"%s"' % installed_path
    suffix = ("".join(" " + a for a in extra_args)) if extra_args else ""
    if installed_path.suffix == ".py":
        interpreter = "python" if IS_WINDOWS else "python3"
        return "%s %s%s" % (interpreter, quoted, suffix)
    if IS_WINDOWS:
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            return '"%s" %s' % (git_bash, quoted)
    return quoted


def load_settings(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def hook_script_path(command):
    """The script a hook command runs, ignoring interpreter and arguments.

    Registrations are matched on this rather than on the whole command string.
    Re-running the installer after the arguments change -- adding --codex, for
    instance -- would otherwise leave the old registration in place beside the
    new one, so the hook runs twice and one of those runs uses the old
    behaviour. Seen for real on 2026-08-20.
    """
    import re as _re
    match = _re.search(r'"([^"]+\.(?:py|sh))"', command) or _re.search(
        r"(\S+\.(?:py|sh))", command)
    return match.group(1).lower() if match else command.lower()


def drop_stale_registrations(settings, event, command, flat=False):
    """Remove entries running the same script with different arguments."""
    script = hook_script_path(command)
    removed = 0
    for entry in list(settings.get("hooks", {}).get(event) or []):
        if flat:
            if isinstance(entry, dict) and entry.get("command") != command                     and hook_script_path(entry.get("command", "")) == script:
                settings["hooks"][event].remove(entry)
                removed += 1
            continue
        kept = [h for h in entry.get("hooks", []) or []
                if h.get("command") == command
                or hook_script_path(h.get("command", "")) != script]
        removed += len(entry.get("hooks", []) or []) - len(kept)
        entry["hooks"] = kept
    for event_entries in (settings.get("hooks", {}).get(event) or [],):
        for entry in list(event_entries):
            if not flat and isinstance(entry, dict) and entry.get("hooks") == []:
                event_entries.remove(entry)
    return removed


def already_registered(settings, event, command):
    for entry in (settings.get("hooks", {}).get(event) or []):
        for hook in entry.get("hooks", []) or []:
            if hook.get("command") == command:
                return True
    return False


def already_registered_cursor(settings, event, command):
    for entry in settings.get("hooks", {}).get(event) or []:
        if isinstance(entry, dict) and entry.get("command") == command:
            return True
    return False


def register_cursor(settings, spec, command):
    """Add one Cursor hook. Cursor uses a flat event -> [{command}] list."""
    settings.setdefault("version", 1)
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault(spec["event"], [])
    definition = {"command": command}
    if spec.get("timeout"):
        definition["timeout"] = spec["timeout"]
    if spec.get("matcher"):
        definition["matcher"] = spec["matcher"]
    entries.append(definition)


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


def robust_rmtree(path):
    """Remove a directory tree, clearing the read-only bit Windows trips over.

    A git checkout or an editor can leave files read-only, and `shutil.rmtree`
    raises PermissionError on those rather than clearing the bit itself.

    What this deliberately does not do is swallow the error. If the tree still
    cannot be removed -- a file held open by another process is the usual
    reason -- the exception propagates, because the caller has to know. A
    half-removed skill folder that gets reported as installed is worse than a
    loud failure.
    """
    def _fix_permission(func, p):
        # Owner-only rwx is all a delete needs. 0o777 also handed every other
        # local account write access to the path for the moment before it
        # disappeared, which is a race worth not having.
        os.chmod(p, stat.S_IRWXU)
        func(p)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda func, p, _exc: _fix_permission(func, p))
    else:
        shutil.rmtree(path, onerror=lambda func, p, _excinfo: _fix_permission(func, p))


def copy_hook_file(source, target):
    """Copy a hook and keep POSIX shell scripts executable across CRLF checkouts."""
    if source.suffix == ".sh":
        target.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        return
    shutil.copyfile(source, target)


def install_skills(args, target_skills_dir):
    sources = select_skills(args.skills)
    if not sources:
        return 0 if sources is not None else 2

    print("\nskills -> %s" % target_skills_dir)
    copied = 0
    failed = 0
    for source in sources:
        target = target_skills_dir / source.name
        if target.exists() and not args.force:
            print("  %-20s already there, left alone (--force to overwrite)" % source.name)
            continue
        if args.dry_run:
            print("  %-20s would copy" % source.name)
            continue
        if target.exists():
            try:
                robust_rmtree(target)
            except OSError as exc:
                # Do not copy over the remains. Merging a new version into an
                # old folder leaves files that no longer exist upstream, and
                # printing "copied" over that is a false completion claim --
                # exactly what this kit exists to prevent.
                print("  %-20s FAILED to replace: %s" % (source.name, exc))
                print("  %-20s left as it was; close whatever holds a file open "
                      "in that folder and re-run" % "")
                failed += 1
                continue
        # dirs_exist_ok covers the case where the directory removal succeeded but
        # the entry lingers for a moment, which Windows does.
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        copied += 1
        print("  %-20s copied" % source.name)

    if copied and not args.dry_run:
        print("  note: checkpoint and neat-freak only produce accurate numbers "
              "once their reference tables match your filing structure.")
    if failed:
        print("\n%d skill folder(s) could not be replaced. Nothing was half-written, "
              "but they are still the old version." % failed)
        return 1
    return 0


def install_for_claude(args):
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

    print("=== Claude Code Installation ===")
    print("target   : %s" % claude_dir)
    print("hooks    : %s" % ", ".join(selected))

    try:
        settings = load_settings(settings_path)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print("settings.json could not be read: %s" % exc)
        return 1

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
            print("%-20s %-12s %s" % (name, spec["event"], command))
            print("%-20s %-12s %s" % ("", "", state))
            planned.append((spec, source, target, command, state))

    if args.dry_run:
        return install_skills(args, claude_dir / "skills")

    hooks_dir.mkdir(parents=True, exist_ok=True)
    for _spec, source, target, _command, _state in planned:
        copy_hook_file(source, target)
        if not IS_WINDOWS:
            # 0o700, not 0o755: these hooks run as the user who installed them
            # and nobody else, so no other local account needs to read or run
            # them. A guardrail kit should not be the thing that widens a
            # permission.
            os.chmod(target, stat.S_IRWXU)
    print("\ncopied %d file(s) into %s" % (len(planned), hooks_dir))

    if settings_path.exists():
        backup_dir = claude_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / ("settings.json.bak-%s" % time.strftime("%Y%m%d-%H%M%S"))
        shutil.copyfile(settings_path, backup)
        print("backed up settings.json to %s" % backup)

    added = 0
    stale = 0
    for spec, _source, _target, command, state in planned:
        # Runs whether or not this exact command is present: an older
        # registration of the same script with different arguments has to go,
        # or the hook runs twice and one of those runs is the old behaviour.
        stale += drop_stale_registrations(settings, spec["event"], command)
    if stale:
        print("removed %d outdated registration(s) of the same script" % stale)
    for spec, _source, _target, command, state in planned:
        if already_registered(settings, spec["event"], command):
            continue
        register(settings, spec, command)
        added += 1

    if added or stale:
        tmp = settings_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, settings_path)
        print("registered %d hook(s), removed %d stale; settings.json re-read and valid"
              % (added, stale))
    else:
        print("nothing new to register in settings.json")

    # The exit code has to carry a skill that could not be replaced, or a
    # caller chaining on `&&` proceeds as if everything installed.
    return install_skills(args, claude_dir / "skills")


def selected_hook_names(args, catalog):
    selected = list(catalog) if args.hooks == "all" else [
        name.strip() for name in args.hooks.split(",") if name.strip()
    ]
    unknown = [name for name in selected if name not in catalog]
    if unknown:
        print("Unknown hook(s): %s" % ", ".join(unknown))
        print("Available: %s" % ", ".join(catalog))
        return None
    return selected


def backup_json(path, backup_root):
    if not path.exists():
        return None
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / ("%s.bak-%s" % (path.name, time.strftime("%Y%m%d-%H%M%S")))
    shutil.copyfile(path, backup)
    print("backed up %s to %s" % (path.name, backup))
    return backup


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def install_for_cursor(args):
    cursor_dir = Path(args.cursor_dir)
    hooks_dir = cursor_dir / "hooks"
    settings_path = cursor_dir / "hooks.json"

    selected = selected_hook_names(args, CURSOR_HOOKS)
    if selected is None:
        return 2

    print("\n=== Cursor Installation ===")
    print("target   : %s" % cursor_dir)
    print("hooks    : %s" % (", ".join(selected) if selected else "(none)"))
    print("note     : Cursor `stop` cannot veto a finished turn; claim-guard "
          "and lint-gate follow up instead of blocking")

    try:
        settings = load_settings(settings_path)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print("hooks.json could not be read: %s" % exc)
        return 1

    planned = []
    for name in selected:
        for spec in CURSOR_HOOKS[name]:
            source = REPO / spec["source"]
            if not source.exists():
                print("SKIP %s -- missing %s" % (name, source))
                continue
            target = hooks_dir / source.name
            command = build_command(target)
            state = "already registered" if already_registered_cursor(
                settings, spec["event"], command
            ) else "will register"
            print("%-20s %-22s %s" % (name, spec["event"], command))
            print("%-20s %-22s %s" % ("", "", state))
            planned.append((spec, source, target, command, state))

    skill_targets = [cursor_dir / "skills"]
    agents_skills = Path.home() / ".agents" / "skills"
    # In `all` mode Codex owns the shared user-level target later in this run.
    # Letting Cursor replace it here as well makes --force delete and copy the
    # same skill twice. Cursor-only installs still merge into an existing
    # shared directory for users who already rely on that layout.
    if args.agent != "all" and agents_skills.exists():
        skill_targets.append(agents_skills)
    if args.dry_run:
        rc = 0
        for target_skills_dir in skill_targets:
            result = install_skills(args, target_skills_dir)
            if result:
                rc = result
        return rc

    hooks_dir.mkdir(parents=True, exist_ok=True)
    for _spec, source, target, _command, _state in planned:
        copy_hook_file(source, target)
        if not IS_WINDOWS:
            # 0o700, not 0o755: these hooks run as the user who installed them
            # and nobody else, so no other local account needs to read or run
            # them. A guardrail kit should not be the thing that widens a
            # permission.
            os.chmod(target, stat.S_IRWXU)
    print("\ncopied %d file(s) into %s" % (len(planned), hooks_dir))

    backup_json(settings_path, cursor_dir / "backups")

    added = 0
    stale = 0
    for spec, _source, _target, command, state in planned:
        stale += drop_stale_registrations(settings, spec["event"], command, flat=True)
    if stale:
        print("removed %d outdated registration(s) of the same script" % stale)
    for spec, _source, _target, command, state in planned:
        if already_registered_cursor(settings, spec["event"], command):
            continue
        register_cursor(settings, spec, command)
        added += 1

    if added or stale:
        write_json_atomic(settings_path, settings)
        print("registered %d hook(s), removed %d stale; hooks.json re-read and valid"
              % (added, stale))
    else:
        print("nothing new to register in hooks.json")

    rc = 0
    for target_skills_dir in skill_targets:
        target_skills_dir.mkdir(parents=True, exist_ok=True)
        result = install_skills(args, target_skills_dir)
        if result:
            rc = result
    return rc


def install_for_codex(args):
    codex_dir = Path(args.codex_dir)
    hooks_dir = codex_dir / "hooks"
    settings_path = codex_dir / "hooks.json"
    key = "windows" if IS_WINDOWS else "posix"

    selected = selected_hook_names(args, CODEX_HOOKS)
    if selected is None:
        return 2

    print("\n=== OpenAI Codex Installation ===")
    print("target   : %s" % codex_dir)
    print("hooks    : %s" % (", ".join(selected) if selected else "(none)"))
    print("note     : hooks are enabled by default; if disabled, set [features].hooks = true")
    print("note     : after a registration change, open /hooks to review and trust the current definition")

    try:
        settings = load_settings(settings_path)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        print("hooks.json could not be read: %s" % exc)
        return 1

    planned = []
    for name in selected:
        for spec in CODEX_HOOKS[name]:
            source = REPO / spec["source"][key]
            if not source.exists():
                print("SKIP %s -- missing %s" % (name, source))
                continue
            target = hooks_dir / source.name
            command = build_command(target, spec.get("args_windows", ()) if IS_WINDOWS else ())
            state = "already registered" if already_registered(
                settings, spec["event"], command
            ) else "will register"
            print("%-20s %-12s %s" % (name, spec["event"], command))
            print("%-20s %-12s %s" % ("", "", state))
            planned.append((spec, source, target, command, state))

    skills_dir = Path.home() / ".agents" / "skills"
    if args.dry_run:
        return install_skills(args, skills_dir)

    hooks_dir.mkdir(parents=True, exist_ok=True)
    for _spec, source, target, _command, _state in planned:
        copy_hook_file(source, target)
        if not IS_WINDOWS:
            # 0o700, not 0o755: these hooks run as the user who installed them
            # and nobody else, so no other local account needs to read or run
            # them. A guardrail kit should not be the thing that widens a
            # permission.
            os.chmod(target, stat.S_IRWXU)
    print("\ncopied %d file(s) into %s" % (len(planned), hooks_dir))

    backup_json(settings_path, codex_dir / "backups")

    added = 0
    stale = 0
    for spec, _source, _target, command, state in planned:
        # Runs whether or not this exact command is present: an older
        # registration of the same script with different arguments has to go,
        # or the hook runs twice and one of those runs is the old behaviour.
        stale += drop_stale_registrations(settings, spec["event"], command)
    if stale:
        print("removed %d outdated registration(s) of the same script" % stale)
    for spec, _source, _target, command, state in planned:
        if already_registered(settings, spec["event"], command):
            continue
        register(settings, spec, command)
        added += 1

    if added or stale:
        write_json_atomic(settings_path, settings)
        print("registered %d hook(s), removed %d stale; hooks.json re-read and valid"
              % (added, stale))
    else:
        print("nothing new to register in hooks.json")

    skills_dir.mkdir(parents=True, exist_ok=True)
    return install_skills(args, skills_dir)


def install_for_antigravity(args):
    print("\n=== Google Antigravity (AGY) Installation ===")
    gemini_dir = Path.home() / ".gemini"
    skills_target = gemini_dir / "config" / "skills"
    print("target   : %s" % skills_target)
    if not args.dry_run:
        skills_target.mkdir(parents=True, exist_ok=True)
    return install_skills(args, skills_target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="claude",
        choices=["claude", "antigravity", "cursor", "codex", "all"],
        help="Automated target: claude, antigravity, cursor, codex, or all (default: claude)",
    )
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
    parser.add_argument(
        "--cursor-dir",
        default=str(Path.home() / ".cursor"),
    )
    parser.add_argument(
        "--codex-dir",
        default=os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("platform : %s" % platform.system())
    if args.dry_run:
        print("mode     : dry run, nothing will be written\n")

    rc = 0
    if args.agent in ("claude", "all"):
        rc = install_for_claude(args)
        if rc != 0:
            return rc
    if args.agent in ("antigravity", "all"):
        rc = install_for_antigravity(args)
        if rc != 0:
            return rc
    if args.agent in ("cursor", "all"):
        rc = install_for_cursor(args)
        if rc != 0:
            return rc
    if args.agent in ("codex", "all"):
        rc = install_for_codex(args)
        if rc != 0:
            return rc

    if not args.dry_run:
        print("\nInstallation finished.")
        print("Run `python scripts/verify-install.py` to verify.")
        print(
            "\nNote: this copies hook scripts over the top of any existing ones, so "
            "settings edited inside a script are lost.\nPer-hook settings that must "
            "survive a reinstall go in a JSON file beside the script, which this "
            "installer never writes\n(no-emoji-guard.json, .lint-gate.json)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
