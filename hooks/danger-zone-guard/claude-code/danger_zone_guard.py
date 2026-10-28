#!/usr/bin/env python3
"""danger_zone_guard.py -- blocks catastrophic or out-of-boundary commands.

PreToolUse hook for Bash tool calls. Catches three classes of dangerous patterns:

  1. Catastrophic directory deletions (e.g., rm -rf / , rm -rf ~ , rmdir /s /q C:\\ , rd /s /q %USERPROFILE% , deleting .git)
  2. Dangerous Git force operations on primary branches (e.g., git push --force origin main/master)
  3. Plaintext exfiltration or dangerous transmission of secret files (e.g., curl -d @.env , sending id_rsa)

Non-destructive operations, standard branch git push, and normal project-local deletions
are allowed.

Two different readings of quotes, on purpose:

  - For deletions, a quoted argument is a normal way to write the command:
    `rm -rf "$HOME"` deletes exactly as much as `rm -rf $HOME`. Blanking the
    quoted text would let anyone bypass this guard by adding two characters,
    so quotes are removed and the result is matched at a command position
    only -- meaning the start of the command or just after `;`, `&&`, `||` or
    a pipe. That is what keeps `echo "rm -rf /"` from being read as a deletion.
  - For force pushes and credential exfiltration, quoted text really is text
    (`git commit -m "reverted that git push --force"`), so those two checks
    run against a copy with quoted spans blanked out.

Heredoc bodies are blanked for every check: they are data being written, not
commands being run.

Known limit: a command hidden behind an interpreter (`bash -c "rm -rf /"`) is
not detected. This is a speed bump against catastrophic mistakes, not a
sandbox against a determined bypass.

Cross-platform: pure Python standard library, no external dependencies. The
same file serves Windows, macOS, and Linux.
Register on PreToolUse with matcher `Bash`. Exit 0 lets the call through,
exit 2 blocks it and outputs the explanation to stderr.
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


# 1. Catastrophic recursive deletion.
# The prefix accepts a command position only -- start of input, or just after a
# separator -- so that `echo rm -rf /` (an argument, not a command) is not a
# match. An optional `sudo` may sit in between.
DANGEROUS_RM = re.compile(
    r"(?:^|[|;&\n]|&&|\|\|)\s*(?:sudo\s+)?("
    r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(?:/|~|\$HOME|/root|/\*|~/\*|\.\.(?:/|\\|\s|$))"
    r"|rm\s+-[a-zA-Z]*f[a-zA-Z]*r?\s+(?:/|~|\$HOME|/root|/\*|~/\*|\.\.(?:/|\\|\s|$))"
    r"|del\s+(?:/[a-zA-Z]+\s*)+\s*(?:[A-Za-z]:[\\/]|%USERPROFILE%|~|\.\.)"
    r"|rd\s+(?:/[a-zA-Z]+\s*)+\s*(?:[A-Za-z]:[\\/]|%USERPROFILE%|~|\.\.)"
    r"|rmdir\s+(?:/[a-zA-Z]+\s*)+\s*(?:[A-Za-z]:[\\/]|%USERPROFILE%|~|\.\.)"
    r"|rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+.*\.git(?:\s|$|/)"
    r"|rd\s+(?:/[a-zA-Z]+\s*)+.*\.git(?:\s|$|\\)"
    r")(?:\s|$|[;&|])",
    re.IGNORECASE,
)

# 2. Dangerous Git force push to main / master
# The segment of one `git push` command: from `push` to the next separator.
# Options git takes before the subcommand (`git -C repo push`) are skipped.
# Linear-time: an option-looking token after `-C` is never taken as its value, so
# `-C -C -C ...` has one parse (it used to have exponentially many).
_GIT_OPT = r"--?[A-Za-z][\w-]*(?:=\S+)?"
GIT_PUSH = re.compile(
    r"\bgit\s+(?:(?:-[Cc]\s+(?:\"\s*\"|'\s*'|(?!" + _GIT_OPT + r"\s)\S+)|" + _GIT_OPT + r")\s+)*push\b([^;&|\n]*)",
    re.IGNORECASE,
)
PROTECTED_BRANCHES = frozenset({"main", "master", "prod", "production", "release"})

# 3. Secret / credential exfiltration patterns
# Escape hatch for the force-push rule only, mirroring fork_pr_guard's
# `# upstream-ok:`. A force push to main is sometimes the operation that was
# actually ordered -- squashing a repo's history, for one -- and a guard with no
# way through invites the far worse habit of routing around it (`git push
# origin +main`, or the REST refs API, neither of which this regex sees).
#
# The marker demands a written reason, so the intent is recorded in the command
# itself, and it is read from the *unblanked* command: it is a comment, and
# blank_quoted would erase it if the reason were quoted. It deliberately does
# not cover the deletion or exfiltration rules -- there is no legitimate
# `rm -rf /`.
FORCE_PUSH_OK = re.compile(r"#\s*force-push-ok:\s*\S", re.IGNORECASE)

SECRET_EXFIL = re.compile(
    r"\b("
    r"curl\s+.*(?:-d|--data|-F|--form)\s+[@\'\"]?(?:\.env|id_rsa|id_ed25519|credentials\.json)"
    r"|nc\s+.*<\s*(?:\.env|id_rsa|id_ed25519)"
    r"|wget\s+--post-(?:file|data)=.*(?:\.env|id_rsa)"
    r")\b",
    re.IGNORECASE,
)

HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

MESSAGE_TEMPLATE = (
    "DANGER ZONE GUARD: Blocked potentially destructive or unsafe command.\n"
    "Matched risk pattern: {reason}\n"
    "Command: {cmd}\n\n"
    "Guidance:\n"
    "  - If cleaning artifacts, scope deletions strictly to workspace subdirectories.\n"
    "  - If pushing changes, avoid forced pushes to main/master; use standard branches.\n"
    "  - Never transmit .env or private key files externally.\n"
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


UNBOUNDED_RETRY = re.compile(
    r"(?:(?:^|[|;&\n])\s*while\s+(?:true|:)\s*;"
    r"|(?:^|[|;&\n])\s*for\s*\(\(\s*;\s*;\s*\)\)"
    r"|(?:^|[|;&\n])\s*while\s*\(\s*\$true\s*\)"
    r"|(?:^|[|;&\n])\s*for\s*\(\s*;\s*;\s*\))",
    re.IGNORECASE,
)
BOUNDED_LOOP_OK = re.compile(r"#\s*bounded-loop-ok:\s*\S", re.IGNORECASE)


def blank_heredocs(command):
    """Blank out heredoc bodies. Their contents are data being written."""
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

    return "".join(chars)


def blank_quoted(command):
    """Blank out quoted spans. Used where quoted text really is text."""
    out = list(command)
    quote = None
    for i, ch in enumerate(command):
        if quote is None:
            if ch in "'\"":
                quote = ch
        elif ch == quote:
            quote = None
        else:
            out[i] = " "
    return "".join(out)


def unquote(command):
    """Drop quote characters, keeping what they wrapped.

    `rm -rf "$HOME"` and `rm -rf $HOME` delete the same thing, so the deletion
    check has to see through the quotes. Two characters must never be enough to
    walk past this guard.
    """
    return command.replace('"', " ").replace("'", " ")


def find_force_push(without_heredocs, as_commands):
    """Return the text of a force push to a protected branch, or None.

    The push segments are located in `as_commands` (quoted text blanked, so a
    commit message that mentions a force push is not one). Their arguments are
    then read from the same span of the unblanked text with the quote characters
    dropped, because `git push --force origin "main"` pushes exactly as much as
    the unquoted form. Flag and branch may come in either order.
    """
    for match in GIT_PUSH.finditer(as_commands):
        start, end = match.span(1)
        tokens = without_heredocs[start:end].replace('"', " ").replace("'", " ").split()
        forced = False
        protected = False
        for token in tokens:
            if token.startswith("--"):
                forced = forced or token.lower().startswith("--force")
            elif token.startswith("-"):
                forced = forced or "f" in token[1:].lower()
            else:
                if token.startswith("+"):
                    forced = True
                    token = token[1:]
                branch = token.split(":")[-1]
                if branch.startswith("refs/heads/"):
                    branch = branch[len("refs/heads/"):]
                protected = protected or branch.lower() in PROTECTED_BRANCHES
        if forced and protected:
            return match.group(0).strip()
    return None


def inspect_command(command, repo_root=None):
    """Check command against dangerous patterns. Returns reason string or None."""
    without_heredocs = blank_heredocs(command)

    rm_match = DANGEROUS_RM.search(unquote(without_heredocs))
    if rm_match:
        return "Catastrophic file/directory deletion or .git removal (`%s`)" % rm_match.group(0).strip()

    as_commands = blank_quoted(without_heredocs)

    force_push = find_force_push(without_heredocs, as_commands)
    if force_push and not FORCE_PUSH_OK.search(command):
        return (
            "Forced push to protected branch (`%s`). When the force push is the "
            "operation that was actually asked for, state that in the command "
            "with `# force-push-ok: <reason>`." % force_push
        )

    exfil_match = SECRET_EXFIL.search(as_commands)
    if exfil_match:
        return "Potential credential/secret transmission (`%s`)" % exfil_match.group(0).strip()

    retry_match = UNBOUNDED_RETRY.search(as_commands)
    if retry_match and not BOUNDED_LOOP_OK.search(command):
        return "Unbounded retry / infinite loop construct detected (`%s`). Under loop-policy, iterations must be bounded." % retry_match.group(0).strip()

    return None


# PowerShell is Claude Code's shell tool on Windows when it is enabled.
SHELL_TOOLS = ("Bash", "PowerShell", "Exec", "exec", "shell", "run_command", "Shell")


# Cursor's own event names. `hook_event_name` alone does not identify Cursor:
# Claude Code sends it too (capitalised -- "Stop", "PreToolUse"), so treating
# its presence as "this is Cursor" made the Stop guards emit a Cursor
# follow-up instead of blocking, on the platform they mainly protect.
CURSOR_EVENTS = frozenset({
    "beforeShellExecution", "afterShellExecution", "beforeReadFile",
    "afterFileEdit", "beforeSubmitPrompt", "beforeMCPExecution", "stop",
})


def is_cursor(payload):
    if payload.get("cursor_version"):
        return True
    return payload.get("hook_event_name") in CURSOR_EVENTS


def is_antigravity(payload):
    """Antigravity names its tool call `toolCall` and its session `conversationId`.

    Neither is a field Claude Code, Codex or Cursor send, so either one is a
    reliable sign of the caller -- unlike a field several of them share.
    """
    return isinstance(payload.get("toolCall"), dict) or "conversationId" in payload


def extract_tool_name(payload):
    event = payload.get("hook_event_name") or ""
    if event in ("beforeShellExecution", "afterShellExecution"):
        return "Shell"
    return (
        payload.get("tool_name")
        or (payload.get("toolCall") or {}).get("name")
        or ""
    )


def extract_command(payload):
    event = payload.get("hook_event_name") or ""
    if event in ("beforeShellExecution", "afterShellExecution"):
        return payload.get("command") or ""
    tool_input = (
        payload.get("tool_input")
        or (payload.get("toolCall") or {}).get("args")
        or {}
    )
    if isinstance(tool_input, str):
        return tool_input
    if not isinstance(tool_input, dict):
        tool_input = {}
    return (
        tool_input.get("command")
        or tool_input.get("CommandLine")
        or tool_input.get("cmd")
        or payload.get("command")
        or ""
    )


def allow(payload):
    if is_antigravity(payload):
        # "ask" hands the call to Antigravity's normal permission flow. `decision`
        # is required: an empty `{}` is read as a deny with no reason, and
        # "allow" would auto-approve and skip a prompt the user still wants.
        sys.stdout.write('{"decision": "ask"}')
    elif is_cursor(payload):
        sys.stdout.write(json.dumps({"permission": "allow"}))
    return 0


def deny(payload, msg):
    if is_antigravity(payload):
        # Antigravity reads the verdict from stdout JSON and expects exit 0.
        sys.stdout.write(json.dumps({"decision": "deny", "reason": msg}, ensure_ascii=False))
        return 0
    if is_cursor(payload):
        sys.stdout.write(json.dumps({
            "permission": "deny",
            "agent_message": msg,
            "user_message": msg,
        }, ensure_ascii=False))
        return 2
    sys.stderr.write(msg)
    return 2


def main():
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    tool_name = extract_tool_name(payload)
    command = extract_command(payload)
    if not tool_name and command:
        tool_name = "Shell"
    if tool_name not in SHELL_TOOLS:
        return allow(payload)
    if not command:
        return allow(payload)

    reason = inspect_command(command)
    if reason:
        return deny(
            payload,
            MESSAGE_TEMPLATE.format(reason=reason, cmd=command.strip()[:200]),
        )
    return allow(payload)


if __name__ == "__main__":
    sys.exit(main())
