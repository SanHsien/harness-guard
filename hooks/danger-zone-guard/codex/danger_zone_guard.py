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

# stdout and stderr take the locale codec too. Where that is not UTF-8, a hook
# blocks correctly and then dies with UnicodeEncodeError while printing its own
# message, so the user sees a traceback instead of the reason.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# 1. Catastrophic recursive deletion
DANGEROUS_RM = re.compile(
    # Command position only, so `echo rm -rf /` is an argument, not a command.
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


def main():
    try:
        payload = read_payload()
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
