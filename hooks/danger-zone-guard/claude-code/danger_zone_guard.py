#!/usr/bin/env python3
"""danger_zone_guard.py -- blocks catastrophic or out-of-boundary commands.

PreToolUse hook for Bash tool calls. Catches three classes of dangerous patterns:

  1. Catastrophic directory deletions (e.g., rm -rf / , rm -rf ~ , rmdir /s /q C:\\ , rd /s /q %USERPROFILE% , deleting .git)
  2. Dangerous Git force operations on primary branches (e.g., git push --force origin main/master)
  3. Plaintext exfiltration or dangerous transmission of secret files (e.g., curl -d @.env , sending id_rsa)

Non-destructive operations, standard branch git push, and normal project-local deletions
are allowed. Text mentioning these commands inside quotes or heredocs is stripped to
prevent false positives.

Cross-platform: pure Python standard library, no external dependencies.
Register on PreToolUse with matcher `Bash`. Exit 0 lets the call through,
exit 2 blocks it and outputs the explanation to stderr.
"""
import json
import re
import sys

# 1. Catastrophic recursive deletion
DANGEROUS_RM = re.compile(
    r"(?:^|[|;&\s])("
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


def strip_literals(command):
    """Blank out heredoc bodies and quoted strings to prevent false positives."""
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
    for i, ch in enumerate(blanked):
        if quote is None:
            if ch in "'\"":
                quote = ch
        elif ch == quote:
            quote = None
        else:
            out[i] = " "
    return "".join(out)


def inspect_command(command):
    """Check command against dangerous patterns. Returns reason string or None."""
    cleaned = strip_literals(command)

    rm_match = DANGEROUS_RM.search(cleaned)
    if rm_match:
        return "Catastrophic file/directory deletion or .git removal (`%s`)" % rm_match.group(0).strip()

    git_match = DANGEROUS_GIT.search(cleaned)
    if git_match:
        return "Forced push to protected branch (`%s`)" % git_match.group(0).strip()

    exfil_match = SECRET_EXFIL.search(cleaned)
    if exfil_match:
        return "Potential credential/secret transmission (`%s`)" % exfil_match.group(0).strip()

    return None


def main():
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    if payload.get("tool_name") not in ("Bash", "Exec", "exec", "shell", "run_command"):
        return 0

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or tool_input.get("CommandLine") or tool_input.get("cmd") or ""
    if not command:
        return 0

    reason = inspect_command(command)
    if reason:
        sys.stderr.write(MESSAGE_TEMPLATE.format(reason=reason, cmd=command.strip()[:200]))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
