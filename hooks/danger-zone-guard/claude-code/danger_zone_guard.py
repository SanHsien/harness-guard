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
DANGEROUS_GIT = re.compile(
    r"\bgit\s+push\s+(?:-[a-zA-Z]*f[a-zA-Z]*|--force|--force-with-lease)\b.*?\b(main|master|prod|production|release)\b",
    re.IGNORECASE,
)

# 3. Secret / credential exfiltration patterns
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


def inspect_command(command):
    """Check command against dangerous patterns. Returns reason string or None."""
    without_heredocs = blank_heredocs(command)

    rm_match = DANGEROUS_RM.search(unquote(without_heredocs))
    if rm_match:
        return "Catastrophic file/directory deletion or .git removal (`%s`)" % rm_match.group(0).strip()

    as_commands = blank_quoted(without_heredocs)

    git_match = DANGEROUS_GIT.search(as_commands)
    if git_match:
        return "Forced push to protected branch (`%s`)" % git_match.group(0).strip()

    exfil_match = SECRET_EXFIL.search(as_commands)
    if exfil_match:
        return "Potential credential/secret transmission (`%s`)" % exfil_match.group(0).strip()

    return None


def main():
    try:
        payload = read_payload()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    tool_name = (
        payload.get("tool_name")
        or (payload.get("toolCall") or {}).get("name")
        or ""
    )
    if tool_name not in ("Bash", "Exec", "exec", "shell", "run_command"):
        if "toolCall" in payload:
            sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0

    tool_input = (
        payload.get("tool_input")
        or (payload.get("toolCall") or {}).get("args")
        or {}
    )
    command = (
        tool_input.get("command")
        or tool_input.get("CommandLine")
        or tool_input.get("cmd")
        or ""
    )
    if not command:
        if "toolCall" in payload:
            sys.stdout.write(json.dumps({"decision": "allow"}))
        return 0

    reason = inspect_command(command)
    if reason:
        msg = MESSAGE_TEMPLATE.format(reason=reason, cmd=command.strip()[:200])
        if "toolCall" in payload:
            sys.stdout.write(json.dumps({"decision": "deny", "reason": msg}, ensure_ascii=False))
            return 0
        sys.stderr.write(msg)
        return 2

    if "toolCall" in payload:
        sys.stdout.write(json.dumps({"decision": "allow"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
