"""Hermes plugin: harness-guard's command guards, run in-process.

Hermes has no stdin hook protocol. A plugin registers `pre_tool_call` and is
called as `callback(tool_name=..., args=..., **ids)`; returning
`{"action": "block", "message": ...}` vetoes the call, `None` lets it through.

This file is a thin adapter. The detection code is NOT here -- it is the same
two files every other agent runs, copied next to this one by
`scripts/install.py --agent hermes`:

    danger_zone_guard.py   hooks/danger-zone-guard/claude-code/  -> inspect_command()
    test_gate_guard.py     hooks/test-gate-guard/claude-code/    -> verdict()

Why it is built this way. Until 2026-11-19 the Hermes plugin was a hand-written
copy from 2026-08-29 that the installer did not know about, so every hardening
since then passed it by. Fed the cases the other agents block, it allowed a
remote script piped to `sudo bash`, `irm ... | iex`, `bash <(curl ...)` and both
agent sandbox-bypass flags. Importing the shared files instead of rewriting them
is what keeps that from happening again; `verify-install.py --agent hermes`
checks the copies byte for byte against the checkout.

What is kept from the old plugin (`_legacy_*` below): it refused a few things
the shared guards deliberately allow -- any force push, `git reset --hard`,
broad `git clean`, destructive SQL. A guard is not weakened by a reinstall, so
those still apply here, after the shared checks.

One optional drop-in: a `fork_pr_guard.py` beside this file, exposing
`inspect(command) -> message | None`, is called as well. That guard is not part
of this kit (it names its owner); a maintainer who has one puts it here.

Failure is closed, and says so. If a shared file is missing or will not load,
or a check raises, the command is blocked with a message naming the cause. The
alternative -- returning None -- is how a guard that protects nothing goes
unnoticed.
"""
from __future__ import annotations

import importlib.util
import re
import shlex
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REQUIRED = ("danger_zone_guard", "test_gate_guard")
_OPTIONAL = ("fork_pr_guard",)
_COMMAND_KEYS = ("command", "cmd", "CommandLine")


class _NoReconfigure:
    """Stands in for a std stream while a hook file is imported.

    The hook files call `sys.stdout.reconfigure(encoding="utf-8")` at import,
    which is right for a short-lived hook process and wrong inside a host that
    owns those streams. Everything else is passed straight through.
    """

    def __init__(self, stream):
        object.__setattr__(self, "_stream", stream)

    def __getattr__(self, name):
        if name == "reconfigure":
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "_stream"), name)


def _load(name):
    """Import one sibling hook file. Returns (module, error text)."""
    path = _HERE / (name + ".py")
    if not path.is_file():
        return None, "%s is missing" % path.name
    saved = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = _NoReconfigure(saved[0]), _NoReconfigure(saved[1])
        spec = importlib.util.spec_from_file_location("harness_guard_hermes_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 -- any load failure is reported, not hidden
        return None, "%s did not load (%s: %s)" % (path.name, type(exc).__name__, exc)
    finally:
        sys.stdout, sys.stderr = saved
    return module, ""


_CORE = {}
_LOAD_ERRORS = []
for _name in _REQUIRED:
    _module, _error = _load(_name)
    if _module is None:
        _LOAD_ERRORS.append(_error)
    else:
        _CORE[_name] = _module
for _name in _OPTIONAL:
    if (_HERE / (_name + ".py")).is_file():
        _module, _error = _load(_name)
        if _module is None:
            _LOAD_ERRORS.append(_error)
        else:
            _CORE[_name] = _module


def status():
    """What is loaded -- for the installer's gate and verify-install.py."""
    return {
        "loaded": sorted(_CORE),
        "required": list(_REQUIRED),
        "optional_present": [name for name in _OPTIONAL if name in _CORE],
        "errors": list(_LOAD_ERRORS),
    }


# --- kept from the 2026-08-29 plugin ------------------------------------------
# Not the main line of defence any more; these are the refusals the old plugin
# had that the shared guards do not, kept so this install is never weaker than
# the one it replaces.

_LEGACY_NON_GIT_BLOCKS = (
    (re.compile(r"\b(?:drop\s+(?:database|schema|table)|truncate\s+table)\b", re.I),
     "Refusing destructive database command without an explicit scoped procedure."),
    (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:ba)?sh\b", re.I),
     "Refusing remote-content pipe to shell."),
    (re.compile(r"\b(?:iwr|invoke-webrequest)\b[^\n|]*\|\s*(?:iex|invoke-expression)\b", re.I),
     "Refusing remote-content pipe to PowerShell execution."),
)
_SHELL_ARG = r"(?:'[^']*'|\"[^\"]*\"|[^\s;&|]+)"
_GIT_VALUE_OPTION = r"(?:-C|-c|--git-dir|--work-tree|--namespace|--config-env|--super-prefix|--exec-path)"
_GIT_FLAG_OPTION = (
    r"(?:--no-pager|--paginate|-p|--bare|--no-replace-objects|--literal-pathspecs"
    r"|--no-literal-pathspecs|--glob-pathspecs|--noglob-pathspecs|--icase-pathspecs"
    r"|--no-optional-locks|--no-advice|--no-lazy-fetch)"
)
_GIT_PREFIX = rf"\bgit(?:\s+(?:(?:{_GIT_VALUE_OPTION})(?:\s+|=){_SHELL_ARG}|{_GIT_FLAG_OPTION}))*\s+"
_TEST_CMD = re.compile(
    r"\b("
    r"pytest|tox|nox"
    r"|npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+(?:run\s+)?test|bun\s+(?:test|run\s+test)|deno\s+test"
    r"|jest|vitest|playwright\s+test|cypress\s+run"
    r"|go\s+test|cargo\s+test|dotnet\s+test|mvn\s+test|gradle\s+test|swift\s+test|mix\s+test"
    r"|bundle\s+exec\s+rspec|rspec|phpunit|Invoke-Pester|make\s+(?:test|check)"
    r"|ruff\s+check|mypy|flake8|eslint|tsc(?:\s+--noEmit)?"
    r")\b"
)
_GIT_WRITE = re.compile(_GIT_PREFIX + r"(?:commit|push)\b")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_GIT_VALUE_OPTIONS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--config-env", "--super-prefix", "--exec-path",
}


def _strip_literals(command: str) -> str:
    """Blank heredoc bodies and quoted strings; they are data, not commands."""
    chars = list(command)
    for match in _HEREDOC.finditer(command):
        delimiter = match.group(2)
        body_start = command.find("\n", match.end())
        if body_start == -1:
            continue
        end_match = re.compile(
            r"^\s*" + re.escape(delimiter) + r"\s*$", re.MULTILINE
        ).search(command, body_start)
        body_end = end_match.start() if end_match else len(command)
        for index in range(body_start, body_end):
            if chars[index] != "\n":
                chars[index] = " "
    blanked = "".join(chars)
    out = list(blanked)
    quote = None
    for index, char in enumerate(blanked):
        if quote is None:
            if char in "'\"":
                quote = char
        elif char == quote:
            quote = None
        else:
            out[index] = " "
    return "".join(out)


def _legacy_test_gate_verdict(command: str):
    command = _strip_literals(command)
    for git_match in _GIT_WRITE.finditer(command):
        head = command[:git_match.start()]
        test_matches = list(_TEST_CMD.finditer(head))
        if not test_matches:
            continue
        separator = head[test_matches[-1].end():]
        if "&&" in separator:
            continue
        if ";" not in separator and "\n" not in separator:
            continue
        return test_matches[-1].group(0), git_match.group(0)
    return None


def _shell_commands(command: str):
    """Tokenize executable segments while preserving quoted arguments."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return []
    commands = []
    current = []
    for token in tokens:
        if token and all(char in ";&|\n" for char in token):
            if current:
                commands.append(current)
                current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    return commands


def _basename(token: str) -> str:
    return re.split(r"[\\/]", token)[-1].lower()


def _git_argv(command):
    index = 0
    while index < len(command) and _basename(command[index]) in {"sudo", "command"}:
        index += 1
    if index < len(command) and _basename(command[index]) == "env":
        index += 1
        while index < len(command) and "=" in command[index] and not command[index].startswith("-"):
            index += 1
    if index >= len(command) or _basename(command[index]) not in {"git", "git.exe", "git.cmd", "git.bat"}:
        return None
    return command[index + 1:]


def _git_subcommand(arguments):
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        option = arguments[index]
        index += 2 if option in _GIT_VALUE_OPTIONS else 1
    if index >= len(arguments):
        return None
    return arguments[index].lower(), arguments[index + 1:]


def _legacy_danger_verdict(command: str):
    for segment in _shell_commands(command):
        executable = _basename(segment[0]) if segment else ""
        if executable in {"rm", "rm.exe"}:
            flags = "".join(item.lstrip("-") for item in segment[1:] if item.startswith("-"))
            targets = {item.rstrip("/") or "/" for item in segment[1:] if not item.startswith("-")}
            if "r" in flags and "f" in flags and ({"/", "~"} & targets):
                return "Refusing broad recursive delete of root/home."
        arguments = _git_argv(segment)
        if arguments is None:
            continue
        parsed = _git_subcommand(arguments)
        if parsed is None:
            continue
        subcommand, rest = parsed
        if subcommand == "reset" and "--hard" in rest:
            return "Refusing git reset --hard because it destroys uncommitted work."
        if subcommand == "clean":
            options = [item for item in rest if item.startswith("-")]
            dry_run = "--dry-run" in options or any(
                item.startswith("-") and not item.startswith("--") and "n" in item[1:]
                for item in options
            )
            risky = any(any(flag in item.lstrip("-") for flag in "dfx") for item in options)
            if risky and not dry_run:
                return "Refusing broad git clean; inspect targets and use a narrower cleanup."
        if subcommand == "push" and any(
            item == "-f" or item == "--force" or item.startswith("--force=")
            for item in rest
        ):
            return "Refusing force-push. Use an explicitly approved, scoped recovery plan."
    literal_free = _strip_literals(command)
    for pattern, message in _LEGACY_NON_GIT_BLOCKS:
        if pattern.search(literal_free):
            return message
    return None


# --- the adapter -----------------------------------------------------------------

_JOINED = (
    "`{test}` and `{git}` are joined with `;` or a newline, so the commit or push "
    "still runs when the tests come back red. Use `&&`, or split them into two "
    "calls and check that the first one exited 0."
)


def command_of(args):
    """The command a tool call is about to run, or "" when it carries none.

    Not tied to the tool being named `terminal`: any tool whose arguments carry
    a command is read, so a renamed or added shell tool is covered too.
    """
    if not isinstance(args, dict):
        return ""
    for key in _COMMAND_KEYS:
        value = args.get(key)
        if isinstance(value, (list, tuple)):
            value = " ".join(str(part) for part in value)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def check_command(command):
    """The block message for `command`, or None. Pure: nothing is run or written."""
    if _LOAD_ERRORS:
        return (
            "the guard is not fully installed (%s), so this command was not "
            "inspected and is refused. Reinstall with `python scripts/install.py "
            "--agent hermes` from the harness-guard checkout." % "; ".join(_LOAD_ERRORS)
        )

    hit = _CORE["test_gate_guard"].verdict(command) or _legacy_test_gate_verdict(command)
    if hit:
        # A pipe or a `||` between the tests and the commit needs its own
        # wording; the shared guard writes it. `;` keeps the message it had.
        explain = getattr(_CORE["test_gate_guard"], "explain", None)
        if explain and len(hit) > 2 and hit[2] != "chain":
            return explain(hit).strip()
        return _JOINED.format(test=hit[0], git=hit[1])

    reason = _CORE["danger_zone_guard"].inspect_command(command)
    if reason:
        return "blocked potentially destructive or unsafe command. Matched risk pattern: %s" % reason

    legacy = _legacy_danger_verdict(command)
    if legacy:
        return legacy

    fork_guard = _CORE.get("fork_pr_guard")
    if fork_guard is not None:
        message = fork_guard.inspect(command)
        if message:
            return message
    return None


def _pre_tool_call(tool_name: str = "", args=None, **kwargs):
    del tool_name, kwargs
    command = command_of(args)
    if not command:
        return None
    try:
        message = check_command(command)
    except Exception as exc:  # noqa: BLE001 -- a guard that raised has not cleared the command
        message = (
            "a check failed while reading this command (%s: %s), so it is refused "
            "rather than run uninspected." % (type(exc).__name__, exc)
        )
    if message:
        return {"action": "block", "message": "Harness Guard: " + message}
    return None


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _pre_tool_call)
