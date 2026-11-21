#!/usr/bin/env python3
"""test_gate_guard.py (Codex build) -- blocks a commit chained after a test with `;`.

Identical judging logic to the Claude Code build in the sibling folder. Only
the interface differs, per the table in hooks/README.md:

  - allowing something prints `{}` rather than exiting quietly
  - a block is expressed as {"decision":"block","reason":"..."} on stdout,
    not exit 2 plus stderr
  - the command-running tool may arrive under several names, so all of them
    are accepted

Read the Claude Code build for the full reasoning and the known limits.

Register on PreToolUse in ~/.codex/hooks.json (and set `hooks = true` in
~/.codex/config.toml).
"""
import json
import re
import sys

# stdout and stderr take the locale codec too. Where that is not UTF-8, a hook
# blocks correctly and then dies with UnicodeEncodeError while printing its own
# message, so the user sees a traceback instead of the reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


TEST_CMD = re.compile(
    r"\b(?:"
    r"pytest|tox|nox"
    r"|npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+(?:run\s+)?test|bun\s+(?:test|run\s+test)|deno\s+test"
    r"|jest|vitest|playwright\s+test|cypress\s+run"
    r"|go\s+test|cargo\s+test|dotnet\s+test|mvn\s+test|gradle\s+test|swift\s+test|mix\s+test"
    r"|bundle\s+exec\s+rspec|rspec|phpunit"
    r"|Invoke-Pester"
    r"|make\s+(?:test|check)"
    r"|ruff\s+check|mypy|flake8|eslint|tsc(?:\s+--noEmit)?"
    r")\b"
    # Added 2026-11-21. The incident that led to the pipe rule ran
    # `python -m unittest`, which the list above never had, so the `;` rule
    # could not see it either. `-m` has no word boundary in front of it.
    r"|(?<=\s)-m\s+unittest\b"
    r"|\brun[-_]tests?\.(?:py|sh|ps1|js|ts|cmd|bat)\b"
    r"|\bnode\s+--test\b"
)
# Options git accepts before the subcommand (`git -C repo push`). Quoted option
# values are blanked by strip_literals, so `-C "my repo"` arrives as `-C "       "`.
# Linear-time: an option-looking token after `-C` is never taken as its value, so
# `-C -C -C ...` has one parse (it used to have exponentially many).
_GIT_OPT = r"--?[A-Za-z][\w-]*(?:=\S+)?"
GIT_WRITE = re.compile(
    r"\bgit\s+(?:(?:-[Cc]\s+(?:\"\s*\"|'\s*'|(?!" + _GIT_OPT + r"\s)\S+)|" + _GIT_OPT + r")\s+)*"
    r"(?:commit|push)\b"
)
# `(?<!<)` keeps a here-string (`<<<word`) from being read as a heredoc, which
# would blank everything after it.
HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# A newline right after one of these continues the command; it is not a new one.
# `||` is left out on purpose: `pytest ||\n git push` runs the push only when the
# tests fail.
CONTINUATION = re.compile(r"(?:&&|(?<!\|)\|(?!\|)|\\)[ \t]*\n")
# PowerShell continues a line with a backtick, not a backslash.
CONTINUATION_PS = re.compile(r"(?:&&|(?<!\|)\|(?!\|)|`)[ \t]*\n")
# Unknown shell: a line-ending continuation character is unambiguous either way.
CONTINUATION_ANY = re.compile(r"(?:&&|(?<!\|)\|(?!\|)|\\|`)[ \t]*\n")
# Every name install.py's Codex matcher (`exec|shell|exec_command|shell_command|Bash`)
# lets through has to be here; `shell_command` was missing until 2026-11-19.
SHELL_TOOLS = ("Bash", "shell", "exec", "exec_command", "shell_command", "local_shell")

MESSAGE = (
    "TEST GATE: the test command `{test}` and `{git}` are joined with `;` or a "
    "newline, so the commit still runs when the tests come back red -- this is "
    "the exact shape of a real incident. Join them with `&&` instead, or split "
    "them into two calls and check that the first one exited 0 before "
    "committing."
)

MESSAGE_PIPE = (
    "TEST GATE: `{test}` is piped into `{stage}` before the `&&`. A POSIX shell "
    "gives a pipeline the exit status of its LAST command, so the `&&` is checking "
    "`{stage}`, not the tests, and `{git}` still runs when they come back red -- "
    "this is the exact shape of a real incident (2026-11-21).\n"
    "Write it one of these ways instead:\n"
    "  set -o pipefail; <tests> 2>&1 | tail -5 && git commit ...\n"
    "  <tests> > test.log 2>&1 && tail -5 test.log && git commit ...\n"
    "  or run the tests in one call, check that it exited 0, and commit in the next.\n"
    "A last stage that can only match a green run is accepted as the gate, for "
    "example `... | tail -1 | grep -q '^OK' && git commit ...`.\n"
    "(PowerShell 7 does keep a native command's failure through a pipe; if that is "
    "the shell here, pipe into a cmdlet such as `Select-Object -Last 5`.)\n"
)
MESSAGE_FIRST = (
    "TEST GATE: `{test}` is piped into `Select-Object -First` (or `-Index`) before "
    "the `&&`. PowerShell stops the test command as soon as enough lines have "
    "arrived, before it can report an exit code, so the `&&` passes on a red run "
    "and `{git}` still runs.\n"
    "Write it one of these ways instead:\n"
    "  <tests> 2>&1 | Select-Object -Last 5 && git commit ...\n"
    "  <tests> *> test.log && Get-Content test.log -TotalCount 20 && git commit ...\n"
    "  or run the tests in one call, check that it exited 0, and commit in the next.\n"
)
MESSAGE_PAREN = (
    "TEST GATE: `{test}` runs inside parentheses and is then piped. PowerShell "
    "treats `(command)` as an expression that succeeded, whatever the command's "
    "exit code was, so the `&&` passes on a red run and `{git}` still runs.\n"
    "Drop the parentheses (`<tests> 2>&1 | Select-Object -Last 5 && git commit "
    "...`), or write the output to a file first (`<tests> *> test.log && ...`).\n"
)
MESSAGE_SWALLOW = (
    "TEST GATE: `{test}` is followed by `|| {rescue}`, which succeeds exactly when "
    "the tests fail, so the chain carries on and `{git}` runs on a red run.\n"
    "Drop the `||` part, or make it stop the chain (`|| exit 1`), or split the "
    "work into two calls and check that the first one exited 0.\n"
)


def read_payload():
    """Read the hook payload as bytes and decode UTF-8 explicitly.

    `json.load(sys.stdin)` decodes using whatever encoding the locale hands the
    process. Where that is not UTF-8 -- the default on a Chinese, Japanese, or
    Korean Windows install -- any non-ASCII text in the payload is mangled, the
    JSON fails to parse, and the hook fails open. Silently, and precisely when
    the message or the command is not in English.

    Observed in service on 2026-08-15: a 2.3 KB Stop payload parsed as an empty
    object, so claim-evidence-guard saw no assistant message and let the turn
    end. Reading bytes removes the dependency on the ambient locale entirely.
    """
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        return {}
    return json.loads(raw.decode("utf-8", "replace"))


def strip_literals(command, powershell=False):
    """Blank out heredoc bodies and quoted strings -- those are data, not commands."""
    chars = list(command)

    for match in HEREDOC.finditer(command):
        delimiter = match.group(2)
        body_start = command.find("\n", match.end())
        if body_start == -1:
            continue
        end_match = re.compile(
            r"^\s*" + re.escape(delimiter) + r"\s*$", re.MULTILINE
        ).search(command, body_start)
        body_end = end_match.start() if end_match else len(command)
        for i in range(body_start, body_end):
            if chars[i] != "\n":
                chars[i] = " "

    blanked = "".join(chars)
    out = list(blanked)
    quote = None
    # PowerShell escapes with a backtick; a backslash there is a path character
    # (`"C:\repo\"` closes at its last quote).
    escape = "`" if powershell else "\\"
    skip = False
    for i, ch in enumerate(blanked):
        if skip:
            skip = False  # the character after a backslash is not a quote
            if quote is not None:
                out[i] = " "
        elif ch == escape and quote != "'":
            skip = True
            if quote is not None:
                out[i] = " "
        elif quote is None:
            if ch in "'\"":
                quote = ch
        elif ch == quote:
            quote = None
        else:
            out[i] = " "
    return "".join(out)


def verdict(command, shell=None):
    """Judge a command; `shell` is "posix", "powershell" or None when unknown.

    The two shells disagree on what escapes a quote (backslash vs backtick), so
    a caller that does not say which one it runs gets both readings and a hit in
    either blocks. Over-blocking an ambiguous quote beats letting a red test
    commit.
    """
    modes = {"posix": (False,), "powershell": (True,)}.get(shell, (False, True))
    for powershell in modes:
        hit = _verdict(command, powershell, shell is None)
        if hit:
            return hit
    return None


# -- A gate that cannot close --------------------------------------------------
# `tests && git commit` is only a gate when the left side exits non-zero on a red
# run. Two shapes break that while still reading as an `&&` chain:
#
#   tests | tail -1 && git commit     POSIX: a pipeline exits with the status of
#                                     its last command, unless pipefail is on.
#   tests || true && git commit       `||` turns the failure into a success.
#
# PowerShell 7 is different, and the rule follows what it does rather than what
# bash does. `&&` reads `$?`, and a native command that exits non-zero leaves
# `$?` false wherever it sits in the pipeline, so `tests | Select-Object -Last 5
# && git commit` is a working gate. Measured on 7.7.0 (2026-11-21) with
# Select-Object -Last/-Skip, Out-String, Out-Null, Out-Host, Out-File,
# Select-String, Tee-Object, ForEach-Object, Where-Object, Measure-Object and a
# native `tail`/`head`/`findstr`. Two exceptions were measured the same way:
# `Select-Object -First N` (and `-Index`) stops the upstream command once it has
# enough objects, before there is an exit code to read; and `(tests) | ...` makes
# the call an expression, whose `$?` is true.
# Sources: about_Pipeline_Chain_Operators ("These operators use the $? and
# $LASTEXITCODE variables to determine if a pipeline failed"), about_Automatic_
# Variables ($? for native commands), Select-Object ("PowerShell stops the command
# that generates the objects as soon as the selected number of objects is
# reached"), and the Bash manual, section Pipelines.
_PIPE = re.compile(r"(?<![|>])\|(?!\|)")
_AND_OR = re.compile(r"&&|\|\|")
_PIPEFAIL = re.compile(
    r"\b(?:set|bash|sh|zsh|ksh|dash)\s+(?:[-+]\w+\s+)*([-+])\w*o\s+pipefail\b"
    r"|\bshopt\s+((?:-\w+\s+)+)pipefail\b"
    r"|\b(un)?(setopt)\s+pipe_?fail\b"
)
# What may follow `||` without opening the gate: the chain stops there.
_FAILS = re.compile(r"\s*(?:exit|return|false|throw)\b")
# A stage that only PowerShell has. Names both shells have (`tee`, `sort`) are
# left out on purpose, and so is a bare Verb-Noun test: `apt-get` fits it.
_PS_STAGE = re.compile(
    r"\s*(?:(?:Select|Out|Where|ForEach|Tee|Measure|Sort|Format|Group|Write|Set|Add"
    r"|Export|ConvertTo|ConvertFrom)-[A-Za-z]+|select|sls|oh|ft|fl|where|foreach|measure)\b",
    re.IGNORECASE,
)
_PS_FIRST = re.compile(
    r"\s*(?:Select-Object|select)\b[^|]*?\s-(?:f|fi|fir|firs|first|i|in|ind|inde|index)\b",
    re.IGNORECASE,
)
# These read everything before they emit anything, so a later `-First` cannot
# stop the test command early.
_PS_BUFFERS = re.compile(
    r"\s*(?:Out-String\b(?![^|]*\s-s)|(?:Sort-Object|Measure-Object|Group-Object|measure|group)\b"
    r"|(?:Select-Object|select)\b[^|]*?\s-(?:l|la|las|last)\b)",
    re.IGNORECASE,
)

# A last stage that reads the test output and fails when the success marker is
# missing is a gate of its own: `... | tail -1 | grep -q '^OK' && git push`.
# Replaying 40 local sessions (2026-11-21) found 34 of these among 152 piped
# chains; blocking them would have been a 22% false-positive rate. A grep that
# also matches a red run (`grep -E "^(Ran|OK|FAILED)"`, `grep -v ...`) is a
# filter, not a check, and stays blocked.
_GREP = re.compile(r"\s*(?:grep|egrep|fgrep|rg|findstr)\b")
_GREP_INVERTED = re.compile(r"\s-[A-Za-z]*v\b|--invert-match")
_NO_FAILURES = re.compile(r"\b(?:0|no|zero)\s+(?:fail\w*|error\w*)", re.IGNORECASE)
_SUCCESS_WORD = re.compile(r"\bOK\b|pass|success", re.IGNORECASE)
_FAILURE_WORD = re.compile(r"fail|error|traceback|\bran\b", re.IGNORECASE)


def _asserts_success(stage):
    """Is `stage` (raw text, quotes intact) a grep for a success marker only?"""
    if not _GREP.match(stage) or _GREP_INVERTED.search(stage):
        return False
    rest = _NO_FAILURES.sub(" ", stage)
    if rest == stage and not _SUCCESS_WORD.search(stage):
        return False
    return not _FAILURE_WORD.search(rest)


def _pipefail_on(before):
    """Is pipefail in effect after the text in `before` has run?"""
    on = False
    for match in _PIPEFAIL.finditer(before):
        if match.group(1):
            on = match.group(1) == "-"
        elif match.group(2):
            on = "s" in match.group(2) and "u" not in match.group(2)
        else:
            on = match.group(3) is None
    return on


def _join_lines(head, powershell, any_continuation):
    """Put a continued command on one line, keeping every offset where it was."""
    escapes = r"\\`" if any_continuation else "`" if powershell else r"\\"
    pattern = re.compile(r"(&&|(?<!\|)\|(?!\|))[ \t]*\n|[" + escapes + r"][ \t]*\n")

    def blank(match):
        operator = match.group(1) or ""
        return operator + " " * (len(match.group(0)) - len(operator))

    return pattern.sub(blank, head)


def _open_gate(head, raw, powershell, any_continuation):
    """Why the `&&` chain that ends `head` does not gate on its tests, or None.

    `head` is everything before the git command, literals already blanked;
    `raw` is the same span before blanking (same length, so offsets agree).
    Returns (test, kind, detail); kind is "pipe", "first", "paren" or "swallow".
    """
    head = _join_lines(head, powershell, any_continuation)
    start = max(head.rfind(";"), head.rfind("\n")) + 1
    chain = head[start:]

    pieces = []  # (text, offset in chain, operator after it, where that operator is)
    position = 0
    for match in _AND_OR.finditer(chain):
        pieces.append((chain[position:match.start()], position, match.group(0), match.start()))
        position = match.end()

    def depth(at):
        return chain.count("(", 0, at) - chain.count(")", 0, at)
    # What is left is the pipeline the git command itself sits in; it is not
    # followed by an operator, so it is not a gate to begin with.

    for index, (text, offset, _operator, _where) in enumerate(pieces):
        test = TEST_CMD.search(text)
        if not test:
            continue
        tail = text[test.end():]
        stages = _PIPE.split(tail)
        after = stages[1:]
        tail_at = start + offset + test.end()
        if after and powershell:
            for number, stage in enumerate(after):
                if _PS_FIRST.match(stage) and not any(
                        _PS_BUFFERS.match(earlier) for earlier in after[:number]):
                    return test.group(0), "first", stage.strip()
            if stages[0].count(")") > stages[0].count("("):
                return test.group(0), "paren", after[-1].strip()
        elif after:
            every_stage_is_powershell = all(_PS_STAGE.match(stage) for stage in after)
            last_at = tail_at + [pipe.end() for pipe in _PIPE.finditer(tail)][-1]
            if (not (any_continuation and every_stage_is_powershell)
                    and not _pipefail_on(head[: start + offset + test.start()])
                    and not _asserts_success(raw[last_at: tail_at + len(tail)])):
                return test.group(0), "pipe", after[-1].strip()
        # `a || b && c` groups as `(a || b) && c`: every `||` further along the
        # chain forgives this test, unless what follows it cannot succeed.
        # An `||` inside a group opened after the test belongs to that group:
        # `tests && (git diff --quiet || git commit ...)` still gates on the tests.
        for later in range(index, len(pieces)):
            if pieces[later][2] != "||" or depth(pieces[later][3]) > depth(offset + test.end()):
                continue
            rescue = pieces[later + 1][0] if later + 1 < len(pieces) else chain[position:]
            if not _FAILS.match(rescue):
                return test.group(0), "swallow", rescue.strip()
    return None


def _first_word(text):
    words = text.split()
    return words[0] if words else "the next command"


def explain(hit):
    """The message for a verdict() result."""
    test, git = hit[0], hit[1]
    kind = hit[2] if len(hit) > 2 else "chain"
    detail = hit[3] if len(hit) > 3 else ""
    if kind == "pipe":
        return MESSAGE_PIPE.format(test=test, git=git, stage=_first_word(detail))
    if kind == "first":
        return MESSAGE_FIRST.format(test=test, git=git)
    if kind == "paren":
        return MESSAGE_PAREN.format(test=test, git=git)
    if kind == "swallow":
        return MESSAGE_SWALLOW.format(test=test, git=git, rescue=_first_word(detail))
    return MESSAGE.format(test=test, git=git)


def _verdict(command, powershell, any_continuation=False):
    """Return (test, git, kind, detail) for a command to block, or None."""
    raw = command
    command = strip_literals(command, powershell)
    for git_match in GIT_WRITE.finditer(command):
        head = command[: git_match.start()]
        test_matches = list(TEST_CMD.finditer(head))
        if not test_matches:
            continue
        continuation = (CONTINUATION_ANY if any_continuation
                        else CONTINUATION_PS if powershell else CONTINUATION)
        separator = continuation.sub(" ", head[test_matches[-1].end():])
        # Any `;` or newline between the two lets the commit run after a red
        # test, even when an `&&` also appears (`pytest && echo ok ; git push`).
        if ";" in separator or "\n" in separator:
            return test_matches[-1].group(0), git_match.group(0), "chain", ""
        open_gate = _open_gate(head, raw[: git_match.start()], powershell, any_continuation)
        if open_gate:
            return open_gate[0], git_match.group(0), open_gate[1], open_gate[2]
    return None


def allow():
    sys.stdout.write("{}\n")
    return 0


def main():
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return allow()
    if payload.get("tool_name") not in SHELL_TOOLS:
        return allow()

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or tool_input.get("cmd") or ""
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    if not command:
        return allow()

    hit = verdict(command)
    if hit:
        sys.stdout.write(
            json.dumps(
                {
                    "decision": "block",
                    "reason": explain(hit),
                }
            )
            + "\n"
        )
        return 0
    return allow()


if __name__ == "__main__":
    sys.exit(main())
