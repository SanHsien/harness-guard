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
CURSOR_DIR = Path.home() / ".cursor"
CODEX_DIR = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
SETTINGS = CLAUDE_DIR / "settings.json"
HOOKS_DIR = CLAUDE_DIR / "hooks"

CLAIM_TRACKER = re.compile(r"claim[-_]ledger[-_]tracker\.(py|sh)")
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

        match = re.search(r"([A-Za-z]:[\\/][^\s\"']+|~[\\/][^\s\"']+|[\\/][^\s\"']+)\.(sh|py)", command)
        if match:
            raw = match.group(0)
            path = Path(os.path.expanduser(raw.replace("\\", "/")))
            if not path.exists():
                record(False, "hook file referenced by settings exists", raw)

    # The tracker has to see edits, or a test run followed by more edits still
    # counts as evidence for the code as it is now.
    tracker_matchers = [
        entry.get("matcher") or ""
        for entry in (data.get("hooks") or {}).get("PostToolUse") or []
        if isinstance(entry, dict) and any(
            CLAIM_TRACKER.search(str(hook.get("command") or ""))
            for hook in entry.get("hooks", []) or [] if isinstance(hook, dict))
    ]
    if tracker_matchers:
        ok = any({"Edit", "Write"} <= set(m.split("|")) for m in tracker_matchers)
        record(ok, "claim-ledger-tracker matcher covers Edit and Write",
               "" if ok else "matchers: %s -- re-run install.py to update it" % tracker_matchers)
    return commands


# -- Antigravity environment -----------------------------------------------

# What install.py registers for Antigravity: per hook, its (event, tools the
# matcher must cover, installed script). A matcher of None means a flat event
# (Stop): the handler sits directly in the list and there is no matcher group.
AGY_EXPECT = {
    "anti-doom-loop-guard": [
        ("PreToolUse", {"run_command", "replace_file_content"}, "anti_doom_loop_guard.py")],
    "danger-zone-guard": [("PreToolUse", {"run_command"}, "danger_zone_guard.py")],
    "test-gate-guard": [("PreToolUse", {"run_command"}, "test_gate_guard.py")],
    "no-emoji-guard": [
        ("PreToolUse", {"write_to_file", "replace_file_content", "multi_replace_file_content"},
         "no-emoji-guard.py")],
    "claim-guard": [
        ("PostToolUse", {"run_command", "grep_search", "write_to_file", "replace_file_content"},
         "claim_ledger_tracker.py"),
        ("Stop", None, "claim_evidence_guard.py")],
    "lint-gate": [("Stop", None, "lint_gate.py")],
}
AGY_FLAT = ("SessionStart", "PreInvocation", "PostInvocation", "Stop")


def agy_handlers(entries, flat):
    """(matcher, handler) pairs of one event, in either layout."""
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if flat:
            if "command" in entry:
                yield None, entry
        else:
            for hook in entry.get("hooks") or []:
                if isinstance(hook, dict):
                    yield entry.get("matcher") or "", hook


def agy_layout_problems(name, entry):
    """Why Antigravity would reject this named hook, per its documented layout."""
    problems = []
    for event, value in entry.items():
        if event == "enabled":
            continue
        if event in AGY_FLAT:
            if not isinstance(value, list) or any(
                    not isinstance(h, dict) or not isinstance(h.get("command"), str) for h in value):
                problems.append("%s: %s must be a flat list of handlers with a 'command'" % (name, event))
        elif event in ("PreToolUse", "PostToolUse"):
            handlers = [h for group in (value if isinstance(value, list) else [])
                        if isinstance(group, dict) for h in (group.get("hooks") or [])]
            if not handlers or any(not isinstance(h, dict) or not isinstance(h.get("command"), str)
                                   for h in handlers):
                problems.append("%s: %s needs groups of {matcher, hooks: [handler]} with a 'command'"
                                % (name, event))
    return problems


def check_antigravity():
    section("Google Antigravity (AGY)")
    skills_dir = GEMINI_DIR / "config" / "skills"
    if skills_dir.exists():
        installed = [p.name for p in skills_dir.iterdir() if p.is_dir()]
        record(True, "Antigravity global skills directory", "%d skills installed (%s)" % (len(installed), ", ".join(installed[:4])))
    else:
        note("Antigravity skills", "not yet populated under %s" % skills_dir)

    path = GEMINI_DIR / "config" / "hooks.json"
    if not path.exists():
        note("Antigravity hooks.json", "does not exist yet at %s (skipped)" % path)
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        record(False, "Antigravity hooks.json is valid JSON", str(exc))
        return
    record(True, "Antigravity hooks.json is valid JSON", str(path))
    if not isinstance(data, dict):
        record(False, "Antigravity hooks.json is a JSON object")
        return
    record("hooks" not in data,
           'Antigravity hooks.json has no Claude Code layout top-level "hooks" key',
           'Antigravity reads every top-level key as a hook name and rejects the whole file, '
           'so none of the hooks in it run' if "hooks" in data else "")
    note("herdr", "herdr's own agent-state hook is separate and not checked here; it uses events "
                  "Antigravity does not have")

    registered = [name for name in AGY_EXPECT if name in data]
    if not registered:
        note("Antigravity hooks", "none of this kit's hooks is registered, skipped")
    for name in registered:
        check_antigravity_hook(name, data[name])


def check_antigravity_hook(name, entry):
    if not isinstance(entry, dict):
        record(False, "Antigravity %s entry is an object" % name)
        return
    problems = agy_layout_problems(name, entry)
    record(not problems, "Antigravity %s uses Antigravity's event layout" % name, "; ".join(problems))
    if entry.get("enabled") is False:
        note("Antigravity %s" % name, 'switched off ("enabled": false), so it protects nothing')

    scripts = {}
    for event, tools, filename in AGY_EXPECT[name]:
        flat = event in AGY_FLAT
        pairs = list(agy_handlers(entry.get(event), flat))
        commands = [h.get("command", "") for _m, h in pairs]
        record(bool(commands), "Antigravity %s is registered on %s" % (name, event),
               "%d handler(s)" % len(commands))
        quoted = [c for c in commands if '"' in c or "'" in c]
        record(not quoted, "Antigravity hook command has no quotes (Antigravity may split it without a shell)",
               ("%s: %s" % (name, quoted[0][:80])) if quoted else "")
        if tools is not None:
            matchers = {m for matcher, _h in pairs for m in matcher.split("|")}
            ok = tools <= matchers
            record(ok, "Antigravity %s matcher covers %s" % (name, ", ".join(sorted(tools))),
                   "" if ok else "matchers: %s" % sorted(matchers))
        script = find_hook_in(GEMINI_DIR / "config" / "hooks", filename)
        record(bool(script), "Antigravity %s script exists (%s)" % (name, filename))
        scripts[filename] = script

    if not all(scripts.values()):
        return
    live_fire_antigravity(name, scripts)


# -- live fire in Antigravity's own payload shape --------------------------------


def agy_common(conversation):
    return {
        "conversationId": conversation,
        "workspacePaths": [str(SCRATCH)],
        "transcriptPath": str(SCRATCH / (conversation + ".jsonl")),
        "artifactDirectoryPath": str(SCRATCH / "artifacts"),
        "modelName": "auto",
    }


def agy_pre(tool, args, conversation="verify-agy"):
    return dict(agy_common(conversation), toolCall={"name": tool, "args": args}, stepIdx=1)


def agy_stop(conversation, reason="NO_TOOL_CALL"):
    return dict(agy_common(conversation), executionNum=1, terminationReason=reason, error="", fullyIdle=True)


def agy_json(proc):
    if proc is None or proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def agy_denies(proc):
    data = agy_json(proc)
    return bool(data) and data.get("decision") == "deny" and bool(data.get("reason"))


def agy_continues(proc):
    data = agy_json(proc)
    return bool(data) and data.get("decision") == "continue" and bool(data.get("reason"))


def agy_defers(proc):
    """A PreToolUse allow: {"decision": "ask"} (an empty `{}` reads as a deny)."""
    if proc is None or proc.returncode != 0:
        return False
    try:
        return json.loads((proc.stdout or "").strip()) == {"decision": "ask"}
    except ValueError:
        return False


def agy_silent(proc):
    """`{}` exactly. {"decision": "allow"} would approve the call without asking."""
    return proc is not None and proc.returncode == 0 and (proc.stdout or "").strip() == "{}"


def agy_env():
    (SCRATCH / "state").mkdir(exist_ok=True)
    return {"HARNESS_GUARD_STATE_DIR": str(SCRATCH / "state")}


def live_fire_antigravity(name, scripts):
    if name == "anti-doom-loop-guard":
        live_fire_doom_loop("antigravity", "Antigravity", scripts["anti_doom_loop_guard.py"])
    elif name in ("danger-zone-guard", "test-gate-guard"):
        script = next(iter(scripts.values()))
        bad, good = (("rm -rf /", "rm -rf dist/") if name == "danger-zone-guard"
                     else ("pytest ; git push", "pytest && git push"))
        blocked = run_hook(script, agy_pre("run_command", {"CommandLine": bad}), env=agy_env())
        allowed = run_hook(script, agy_pre("run_command", {"CommandLine": good}), env=agy_env())
        record(agy_denies(blocked), "Antigravity %s denies `%s`" % (name, bad), process_detail(blocked))
        record(agy_defers(allowed), "Antigravity %s allows `%s` (decision ask)" % (name, good), process_detail(allowed))
    elif name == "no-emoji-guard":
        script = scripts["no-emoji-guard.py"]
        probe = str(SCRATCH / "a.md")
        reason = switched_off(script, probe)
        if reason:
            note("Antigravity no-emoji-guard", "installed and loaded, but switched off (%s), so it "
                 "allows writes. That is a setting, not a fault." % reason)
            return
        blocked = run_hook(script, agy_pre("write_to_file", {
            "TargetFile": probe, "CodeContent": "ship it \U0001F680"}), env=agy_env())
        allowed = run_hook(script, agy_pre("write_to_file", {
            "TargetFile": probe, "CodeContent": "ship it"}), env=agy_env())
        record(agy_denies(blocked), "Antigravity no-emoji-guard denies a write containing emoji",
               process_detail(blocked))
        record(agy_defers(allowed), "Antigravity no-emoji-guard allows a clean write (decision ask)",
               process_detail(allowed))
    elif name == "claim-guard":
        live_fire_antigravity_claim(scripts["claim_ledger_tracker.py"], scripts["claim_evidence_guard.py"])
    elif name == "lint-gate":
        live_fire_antigravity_lint(scripts["lint_gate.py"])


def live_fire_antigravity_claim(tracker, guard):
    def say(conversation, text):
        line = {"index": 1, "type": "PLANNER_RESPONSE", "status": "DONE", "text": text}
        (SCRATCH / (conversation + ".jsonl")).write_text(json.dumps(line) + "\n", encoding="utf-8")

    note("Antigravity claim-guard", "the Stop payload has no assistant message, so the guard reads the "
         "transcript file; its line format is not in the official docs. These checks use a transcript "
         "of the documented step shape -- they prove the adapter, not a real transcript")
    say("verify-agy-empty", "I ran the tests, all passing.")
    empty = run_hook(guard, agy_stop("verify-agy-empty"), env=agy_env())
    record(agy_continues(empty), "Antigravity claim-guard continues 'tests pass' with an empty ledger",
           process_detail(empty))

    say("verify-agy-logged", "I ran the tests, all passing.")
    logged = run_hook(tracker, dict(agy_pre("run_command", {"CommandLine": "pytest -q"}, "verify-agy-logged"),
                                    stepIdx=2), env=agy_env())
    after = run_hook(guard, agy_stop("verify-agy-logged"), env=agy_env())
    record(agy_silent(logged), "Antigravity claim-ledger-tracker answers {}", process_detail(logged))
    record(agy_silent(after), "Antigravity claim-guard allows the same claim once the ledger has a test run",
           process_detail(after))


def live_fire_antigravity_lint(script):
    failing_check = "%s -c \"print('found 3 errors')\"" % sys.executable
    project = SCRATCH / "agy-lint-project"
    quiet = SCRATCH / "agy-quiet-project"
    for directory in (project, quiet):
        directory.mkdir(exist_ok=True)
    (project / ".lint-gate.json").write_text(
        json.dumps({"cmd": failing_check, "fail": "[1-9][0-9]* errors?"}), encoding="utf-8")

    def stop(directory, conversation):
        return dict(agy_stop(conversation), workspacePaths=[str(directory)])

    inert = run_hook(script, stop(quiet, "verify-agy-lint-quiet"), env=agy_env())
    first = run_hook(script, stop(project, "verify-agy-lint"), env=agy_env())
    again = run_hook(script, stop(project, "verify-agy-lint"), env=agy_env())
    record(agy_silent(inert), "Antigravity lint-gate does nothing in a project with no .lint-gate.json",
           process_detail(inert))
    record(agy_continues(first), "Antigravity lint-gate continues when the project's check fails",
           process_detail(first))
    record(agy_silent(again), "Antigravity lint-gate lets the identical failure through the second time",
           process_detail(again))


def check_cursor_config():
    section("Cursor hooks.json")
    path = CURSOR_DIR / "hooks.json"
    if not path.exists():
        note("hooks.json", "does not exist yet at %s (skipped)" % path)
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        record(False, "Cursor hooks.json is valid JSON", str(exc))
        return
    record(True, "Cursor hooks.json is valid JSON", str(path))
    record(data.get("version") == 1, "Cursor hooks.json has version 1")
    hooks = data.get("hooks") or {}
    shell_guards = hooks.get("beforeShellExecution") or []
    tool_guards = hooks.get("preToolUse") or []
    record(
        bool(shell_guards or tool_guards),
        "Cursor has beforeShellExecution or preToolUse guards",
        "%d beforeShellExecution, %d preToolUse entries" % (len(shell_guards), len(tool_guards)),
    )
    for event, entries in hooks.items():
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            command = entry.get("command") or ""
            if IS_WINDOWS and re.match(r"^\s*bash\s", command):
                record(False, "no bare `bash` in a Windows Cursor hook command", command[:70])


def check_codex_config():
    section("Codex hooks.json")
    path = CODEX_DIR / "hooks.json"
    if not path.exists():
        note("hooks.json", "does not exist yet at %s (skipped)" % path)
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        record(False, "Codex hooks.json is valid JSON", str(exc))
        return
    record(True, "Codex hooks.json is valid JSON", str(path))
    commands = list(collect_commands(data.get("hooks")))
    record(bool(commands), "at least one Codex hook is registered", "%d found" % len(commands))
    note(
        "Codex hook trust",
        "this verifier runs hook files directly; use /hooks in Codex to confirm "
        "the current definitions are reviewed and trusted",
    )
    for command in commands:
        if IS_WINDOWS and re.match(r"^\s*bash\s", command):
            record(
                False,
                "no bare `bash` in a Windows Codex hook command",
                command[:70] + " -- resolves to WSL",
            )
        if IS_WINDOWS and "python3 ~/" in command.replace("\\", "/"):
            record(
                False,
                "Codex hook command uses python3 with a tilde path",
                command[:70] + " -- that combination fails open on Windows",
            )


def find_hook_in(directory, *names):
    for name in names:
        path = directory / name
        if path.exists():
            return path
    return None


def codex_blocks(proc):
    """Return whether a Codex hook emitted a supported deny decision."""
    if proc is None:
        return False
    if proc.returncode == 2:
        return bool((proc.stderr or "").strip())
    try:
        data = json.loads(proc.stdout or "{}")
    except (TypeError, ValueError):
        return False
    if data.get("decision") == "block":
        return True
    specific = data.get("hookSpecificOutput") or {}
    return specific.get("permissionDecision") == "deny"


def process_detail(*processes):
    """Keep failed live-fire diagnostics useful without dumping unbounded output."""
    parts = []
    for proc in processes:
        if proc is None:
            parts.append("not run")
            continue
        stdout = (proc.stdout or "").strip().replace("\n", "\\n")[:160]
        stderr = (proc.stderr or "").strip().replace("\n", "\\n")[:160]
        parts.append("exit=%s stdout=%r stderr=%r" % (proc.returncode, stdout, stderr))
    return " | ".join(parts)


# -- anti-doom-loop-guard, one live fire for every agent ------------------------

DOOM_HOOK = "anti_doom_loop_guard.py"


def _doom_payloads(agent):
    """(command payload for a given command, an edit payload) in the agent's own shape."""
    if agent == "codex":
        return (
            lambda cmd: {"session_id": "verify-doom", "turn_id": "t1", "hook_event_name": "PreToolUse",
                         "tool_name": "Bash", "tool_input": {"command": cmd}},
            {"session_id": "verify-doom", "turn_id": "t1", "hook_event_name": "PreToolUse",
             "tool_name": "apply_patch",
             "tool_input": {"command": "*** Begin Patch\n*** End Patch"}},
        )
    if agent == "cursor":
        return (
            lambda cmd: {"hook_event_name": "preToolUse", "cursor_version": "1.0",
                         "conversation_id": "verify-doom", "tool_name": "Shell",
                         "tool_input": {"command": cmd}},
            {"hook_event_name": "preToolUse", "cursor_version": "1.0",
             "conversation_id": "verify-doom", "tool_name": "Write",
             "tool_input": {"path": "probe.txt", "contents": "x"}},
        )
    if agent == "antigravity":
        return (
            lambda cmd: {"toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                         "stepIdx": 1, "conversationId": "verify-doom"},
            {"toolCall": {"name": "replace_file_content", "args": {"TargetFile": "probe.txt"}},
             "stepIdx": 2, "conversationId": "verify-doom"},
        )
    return (
        lambda cmd: {"session_id": "verify-doom", "hook_event_name": "PreToolUse",
                     "tool_name": "Bash", "tool_input": {"command": cmd}},
        {"session_id": "verify-doom", "hook_event_name": "PreToolUse", "tool_name": "Edit",
         "tool_input": {"file_path": "probe.txt", "old_string": "a", "new_string": "b"}},
    )


def doom_denies(agent, proc):
    """Did the guard say no in this agent's own deny format?"""
    if proc is None:
        return False
    if agent == "claude":
        return proc.returncode == 2 and bool((proc.stderr or "").strip())
    try:
        data = json.loads(proc.stdout or "{}")
    except (TypeError, ValueError):
        return False
    if proc.returncode != 0 or not isinstance(data, dict):
        return False
    if agent == "codex":
        return data.get("decision") == "block"
    if agent == "cursor":
        return data.get("permission") == "deny"
    return data.get("decision") == "deny"


def live_fire_doom_loop(agent, label, script, args=()):
    """Alternating command/edit must pass; three identical commands in a row must be denied."""
    command_payload, edit_payload = _doom_payloads(agent)
    state = SCRATCH / ("doom-%s.json" % agent)
    env = {
        "ANTI_DOOM_LOOP_STATE_FILE": str(state),
        "ANTI_DOOM_LOOP_LOG_FILE": str(SCRATCH / ("doom-%s.jsonl" % agent)),
        "ANTI_DOOM_LOOP_THRESHOLD": "3",
    }
    if state.exists():
        state.unlink()

    alternating = []
    for _ in range(3):
        alternating.append(run_hook(script, command_payload("pytest -q"), env=env, args=args))
        run_hook(script, edit_payload, env=env, args=args)
    repeated = [run_hook(script, command_payload("npm run build"), env=env, args=args) for _ in range(3)]
    if any(proc is None for proc in alternating + repeated):
        record(False, "%s anti-doom-loop-guard runs" % label)
        return
    allowed_ok = all(proc.returncode == 0 and not doom_denies(agent, proc) for proc in alternating)
    record(
        allowed_ok,
        "%s anti-doom-loop-guard allows a command repeated with edits in between" % label,
        "" if allowed_ok else process_detail(*alternating[-1:]),
    )
    blocked_ok = (not doom_denies(agent, repeated[0]) and not doom_denies(agent, repeated[1])
                  and doom_denies(agent, repeated[2]))
    record(
        blocked_ok,
        "%s anti-doom-loop-guard blocks the third identical command in a row" % label,
        "" if blocked_ok else process_detail(*repeated),
    )


def check_codex_live_fire():
    hooks_dir = CODEX_DIR / "hooks"
    settings_path = CODEX_DIR / "hooks.json"
    if not settings_path.exists():
        note("Codex hooks", "not installed, skipped")
        return
    try:
        with open(settings_path, encoding="utf-8") as fh:
            hooks_block = json.load(fh).get("hooks") or {}
            commands = list(collect_commands(hooks_block))
    except (OSError, ValueError, UnicodeDecodeError):
        return  # check_codex_config already records the parse failure

    section("Live fire (Codex payload shape)")

    def registered(*names):
        return any(any(name in command for name in names) for command in commands)

    def registered_command(*names):
        return next(
            (command for command in commands if any(name in command for name in names)),
            "",
        )

    def registered_args(*names):
        command = registered_command(*names)
        return ("--codex",) if "--codex" in command else ()

    def registered_matchers(*names):
        matchers = []
        for entries in hooks_block.values():
            for entry in entries or []:
                matcher = entry.get("matcher") or ""
                for hook in entry.get("hooks", []) or []:
                    command = hook.get("command") or ""
                    if any(name in command for name in names):
                        matchers.append(matcher)
        return matchers

    if registered(DOOM_HOOK):
        doom = find_hook_in(hooks_dir, DOOM_HOOK)
        if not doom:
            record(False, "Codex anti-doom-loop-guard script exists")
        else:
            doom_command = registered_command(DOOM_HOOK)
            record("--agent codex" in doom_command,
                   "Codex anti-doom-loop-guard is registered with --agent codex",
                   "" if "--agent codex" in doom_command else doom_command[:80])
            doom_matchers = registered_matchers(DOOM_HOOK)
            doom_ok = any({"Bash", "apply_patch"} <= set(m.split("|")) for m in doom_matchers)
            record(doom_ok, "Codex anti-doom-loop-guard matcher covers Bash and apply_patch",
                   "" if doom_ok else "matchers: %s" % (doom_matchers or ["<missing>"]))
            live_fire_doom_loop("codex", "Codex", doom, args=("--agent", "codex"))

    tracker_names = ("claim_ledger_tracker.py", "claim-ledger-tracker.sh")
    guard_names = ("claim_evidence_guard.py", "claim-evidence-guard.sh")
    if registered(*tracker_names, *guard_names):
        tracker = find_hook_in(hooks_dir, *tracker_names)
        guard = find_hook_in(hooks_dir, *guard_names)
        record(
            bool(tracker and guard),
            "Codex claim-guard is installed as a pair",
            "installing only one silently disables the feature",
        )
        if tracker and guard:
            tracker_matchers = registered_matchers(*tracker_names)
            required_aliases = {"exec_command", "shell_command", "apply_patch"}
            matcher_ok = any(
                required_aliases.issubset(set(matcher.split("|")))
                for matcher in tracker_matchers
            )
            record(
                matcher_ok,
                "Codex claim tracker matcher accepts exec_command, shell_command and apply_patch",
                ""
                if matcher_ok
                else "matchers: %s" % (tracker_matchers or ["<missing>"]),
            )
            empty = run_hook(
                guard,
                {
                    "session_id": "verify-codex-claim-empty",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "I ran the tests; all passing.",
                },
                args=registered_args(*guard_names),
            )
            logged = run_hook(
                tracker,
                {
                    "session_id": "verify-codex-claim-logged",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest -q"},
                    "tool_response": {"exit_code": 0},
                },
                args=registered_args(*tracker_names),
            )
            after = run_hook(
                guard,
                {
                    "session_id": "verify-codex-claim-logged",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "I ran the tests; all passing.",
                },
                args=registered_args(*guard_names),
            )
            if empty is None or logged is None or after is None:
                record(False, "Codex claim-guard runs")
            else:
                record(codex_blocks(empty), "Codex claim-guard blocks an unsupported test claim")
                claim_allowed = (
                    logged.returncode == 0
                    and after.returncode == 0
                    and not codex_blocks(after)
                )
                record(
                    claim_allowed,
                    "Codex claim-guard allows the claim after recording a test run",
                    "" if claim_allowed else process_detail(logged, after),
                )

                alias_failures = []
                for tool_name in ("exec_command", "shell_command"):
                    alias_session = "verify-codex-claim-%s" % tool_name
                    alias_logged = run_hook(
                        tracker,
                        {
                            "session_id": alias_session,
                            "hook_event_name": "PostToolUse",
                            "tool_name": tool_name,
                            "tool_input": {"cmd": "pytest -q"},
                            "tool_response": {"exit_code": 0},
                        },
                        args=registered_args(*tracker_names),
                    )
                    alias_after = run_hook(
                        guard,
                        {
                            "session_id": alias_session,
                            "hook_event_name": "Stop",
                            "last_assistant_message": "I ran the tests; all passing.",
                        },
                        args=registered_args(*guard_names),
                    )
                    if (
                        alias_logged is None
                        or alias_after is None
                        or alias_logged.returncode != 0
                        or alias_after.returncode != 0
                        or codex_blocks(alias_after)
                    ):
                        alias_failures.append(tool_name)
                record(
                    not alias_failures,
                    "Codex claim tracker accepts exec_command and shell_command",
                    "" if not alias_failures else "failed: %s" % ", ".join(alias_failures),
                )

    lint_names = ("lint_gate.py", "lint-gate.sh")
    if registered(*lint_names):
        lint_gate = find_hook_in(hooks_dir, *lint_names)
        if not lint_gate:
            record(False, "Codex lint-gate script exists")
        else:
            fake_check = "%s -c \"print('found 3 errors')\"" % sys.executable
            lint_env = {"LINT_CMD": fake_check, "FAIL_PATTERN": "[1-9][0-9]* errors?"}
            lint_args = registered_args(*lint_names)
            failing = run_hook(
                lint_gate,
                {
                    "session_id": "verify-codex-lint",
                    "hook_event_name": "Stop",
                    "cwd": str(SCRATCH),
                    "stop_hook_active": False,
                },
                env=lint_env,
                args=lint_args,
            )
            loop = run_hook(
                lint_gate,
                {
                    "session_id": "verify-codex-lint",
                    "hook_event_name": "Stop",
                    "cwd": str(SCRATCH),
                    "stop_hook_active": True,
                },
                env=lint_env,
                args=lint_args,
            )
            if failing is None or loop is None:
                record(False, "Codex lint-gate runs")
            else:
                record(codex_blocks(failing), "Codex lint-gate blocks when its check fails")
                loop_allowed = loop.returncode == 0 and not codex_blocks(loop)
                record(
                    loop_allowed,
                    "Codex lint-gate avoids an infinite Stop loop",
                    "" if loop_allowed else process_detail(loop),
                )

    test_names = ("test_gate_guard.py", "test-gate-guard.py")
    if registered(*test_names):
        test_gate = find_hook_in(hooks_dir, *test_names)
        if not test_gate:
            record(False, "Codex test-gate-guard script exists")
        else:
            chained = run_hook(
                test_gate,
                {
                    "session_id": "verify-codex-test",
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest ; git push"},
                },
            )
            gated = run_hook(
                test_gate,
                {
                    "session_id": "verify-codex-test",
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest && git push"},
                },
            )
            if chained is None or gated is None:
                record(False, "Codex test-gate-guard runs")
            else:
                record(codex_blocks(chained), "Codex test-gate-guard blocks `pytest ; git push`")
                record(
                    gated.returncode == 0 and not codex_blocks(gated),
                    "Codex test-gate-guard allows `pytest && git push`",
                )

    danger_names = ("danger_zone_guard.py", "danger-zone-guard.py")
    if registered(*danger_names):
        danger = find_hook_in(hooks_dir, *danger_names)
        if not danger:
            record(False, "Codex danger-zone-guard script exists")
        else:
            destructive = run_hook(
                danger,
                {
                    "session_id": "verify-codex-danger",
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "rm -rf /"},
                },
            )
            safe = run_hook(
                danger,
                {
                    "session_id": "verify-codex-danger",
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "rm -rf dist/"},
                },
            )
            if destructive is None or safe is None:
                record(False, "Codex danger-zone-guard runs")
            else:
                record(codex_blocks(destructive), "Codex danger-zone-guard blocks `rm -rf /`")
                record(
                    safe.returncode == 0 and not codex_blocks(safe),
                    "Codex danger-zone-guard allows `rm -rf dist/`",
                )

    emoji_names = ("no-emoji-guard.py",)
    if registered(*emoji_names):
        emoji_guard = find_hook_in(hooks_dir, *emoji_names)
        if not emoji_guard:
            record(False, "Codex no-emoji-guard script exists")
        else:
            probe = str(SCRATCH / "codex-emoji-probe.md")
            reason = switched_off(emoji_guard, probe)
            if reason:
                note(
                    "Codex no-emoji-guard",
                    "installed and loaded, but switched off (%s), so it allows writes" % reason,
                )
            else:
                blocked = run_hook(
                    emoji_guard,
                    {
                        "session_id": "verify-codex-emoji",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "command": "*** Begin Patch\n*** Add File: codex-emoji-probe.md\n+ship it \U0001f680\n*** End Patch"
                        },
                        "cwd": str(SCRATCH),
                    },
                )
                allowed = run_hook(
                    emoji_guard,
                    {
                        "session_id": "verify-codex-emoji",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "command": "*** Begin Patch\n*** Add File: codex-emoji-probe.md\n+ship it\n*** End Patch"
                        },
                        "cwd": str(SCRATCH),
                    },
                )
                removal = run_hook(
                    emoji_guard,
                    {
                        "session_id": "verify-codex-emoji",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "command": "*** Begin Patch\n*** Update File: codex-emoji-probe.md\n@@\n-old \U0001f680\n+old\n*** End Patch"
                        },
                        "cwd": str(SCRATCH),
                    },
                )
                exempt = run_hook(
                    emoji_guard,
                    {
                        "session_id": "verify-codex-emoji",
                        "hook_event_name": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "command": "*** Begin Patch\n*** Update File: transcript.srt\n@@\n+raw \U0001f680\n*** End Patch"
                        },
                        "cwd": str(SCRATCH),
                    },
                )
                if any(proc is None for proc in (blocked, allowed, removal, exempt)):
                    record(False, "Codex no-emoji-guard runs")
                else:
                    record(codex_blocks(blocked), "Codex no-emoji-guard blocks an emoji write")
                    record(
                        allowed.returncode == 0 and not codex_blocks(allowed),
                        "Codex no-emoji-guard allows a clean write",
                    )
                    record(
                        removal.returncode == 0 and not codex_blocks(removal),
                        "Codex no-emoji-guard allows removing an existing emoji",
                    )
                    record(
                        exempt.returncode == 0 and not codex_blocks(exempt),
                        "Codex no-emoji-guard allows an exempt patch path",
                    )


def check_cursor_live_fire():
    hooks_dir = CURSOR_DIR / "hooks"
    if not hooks_dir.exists():
        note("Cursor hooks", "not installed, skipped")
        return
    section("Live fire (Cursor payload shape)")
    doom = find_hook_in(hooks_dir, DOOM_HOOK)
    if doom:
        registered = False
        try:
            with open(CURSOR_DIR / "hooks.json", encoding="utf-8") as fh:
                pre = (json.load(fh).get("hooks") or {}).get("preToolUse") or []
            registered = any(isinstance(e, dict) and DOOM_HOOK in (e.get("command") or "")
                             and {"Shell", "Write"} <= set((e.get("matcher") or "").split("|"))
                             for e in pre)
        except (OSError, ValueError, UnicodeDecodeError):
            pass
        record(registered, "Cursor anti-doom-loop-guard is registered on preToolUse for Shell, Read and Write")
        live_fire_doom_loop("cursor", "Cursor", doom)
    test_gate = find_hook_in(hooks_dir, "test_gate_guard.py")
    danger = find_hook_in(hooks_dir, "danger_zone_guard.py")
    if test_gate:
        chained = run_hook(
            test_gate,
            {
                "hook_event_name": "beforeShellExecution",
                "cursor_version": "1.0",
                "command": "pytest ; git push",
            },
        )
        gated = run_hook(
            test_gate,
            {
                "hook_event_name": "beforeShellExecution",
                "cursor_version": "1.0",
                "command": "pytest && git push",
            },
        )
        if chained and gated:
            record(
                '"permission": "deny"' in (chained.stdout or "") or chained.returncode == 2,
                "Cursor test-gate-guard blocks `pytest ; git push`",
            )
            record(
                '"permission": "deny"' in (chained.stdout or ""),
                "Cursor test-gate-guard returns permission deny JSON",
            )
            record(gated.returncode == 0, "Cursor test-gate-guard allows `pytest && git push`")
        else:
            record(False, "Cursor test-gate-guard runs")
    if danger:
        destructive = run_hook(
            danger,
            {
                "hook_event_name": "beforeShellExecution",
                "cursor_version": "1.0",
                "command": "rm -rf /",
            },
        )
        safe = run_hook(
            danger,
            {
                "hook_event_name": "beforeShellExecution",
                "cursor_version": "1.0",
                "command": "rm -rf dist/",
            },
        )
        if destructive and safe:
            record(
                '"permission": "deny"' in (destructive.stdout or "") or destructive.returncode == 2,
                "Cursor danger-zone-guard blocks `rm -rf /`",
            )
            record(safe.returncode == 0, "Cursor danger-zone-guard allows `rm -rf dist/`")
        else:
            record(False, "Cursor danger-zone-guard runs")


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


def check_anti_doom_loop_guard():
    hook = find_hook(DOOM_HOOK)
    if not hook:
        note("anti-doom-loop-guard", "not installed, skipped")
        return
    live_fire_doom_loop("claude", "Claude Code", hook)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="all",
        choices=["claude", "antigravity", "cursor", "codex", "all"],
    )
    _args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("Verifying the harness installation...")
    jq = check_environment()
    if _args.agent in ("claude", "all"):
        check_settings(jq)
    if _args.agent in ("antigravity", "all"):
        check_antigravity()
    if _args.agent in ("cursor", "all"):
        check_cursor_config()
    if _args.agent in ("codex", "all"):
        check_codex_config()

    if _args.agent in ("claude", "all"):
        section("Live fire (each installed hook is run with a synthetic payload)")
        check_no_emoji_guard()
        check_claim_guard()
        check_lint_gate()
        check_test_gate()
        check_danger_zone_guard()
        check_anti_doom_loop_guard()
    if _args.agent in ("cursor", "all"):
        check_cursor_live_fire()
    if _args.agent in ("codex", "all"):
        check_codex_live_fire()

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
