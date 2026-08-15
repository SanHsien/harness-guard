#!/usr/bin/env python3
"""danger_zone_guard.py -- Codex version of danger-zone-guard.

PreToolUse hook for Codex exec/shell tool calls. Catches catastrophic deletions,
force pushes to protected branches, and dangerous secret transmissions.

Codex protocol:
  - Allowed: print `{}` and exit 0
  - Blocked: print `{"decision": "block", "reason": "..."}` and exit 0
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


def strip_literals(command):
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
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        sys.stdout.write("{}\n")
        return 0

    tool_name = payload.get("tool_name") or ""
    if tool_name not in ("exec", "shell", "exec_command", "Bash", "Exec"):
        sys.stdout.write("{}\n")
        return 0

    tool_input = payload.get("tool_input") or {}
    command = (
        tool_input.get("command")
        or tool_input.get("cmd")
        or tool_input.get("CommandLine")
        or ""
    )
    if not command:
        sys.stdout.write("{}\n")
        return 0

    reason = inspect_command(command)
    if reason:
        msg = (
            "DANGER ZONE GUARD: Potentially destructive or unsafe command blocked: "
            "%s. (Command: %s)" % (reason, command.strip()[:160])
        )
        sys.stdout.write(json.dumps({"decision": "block", "reason": msg}, ensure_ascii=False))
        return 0

    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
