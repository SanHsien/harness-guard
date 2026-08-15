> English | [中文版](windows-install.md)

# Installing on Windows

The instructions in the main README assume macOS or Linux. On Windows, three of
those steps do not work, and none of the three tells you it failed. This page
is the Windows path.

Everything here was checked on a real Windows 11 machine, not inferred from
documentation.

---

## What breaks, and why it is silent

### 1. `jq` is not there

All three shell hooks parse their input with `jq`. A stock Windows install has
no `jq`, and `winget install jqlang.jq` is an extra step most people skip.

The failure is the bad kind. `claim-evidence-guard.sh` reads its input like
this:

```bash
SID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null) || exit 0
```

No `jq` means exit 0 means "allow." No error, no message, nothing in the log.
The hook is registered, the config looks right, and it protects nothing.

### 2. A bare `bash` is WSL, not Git Bash

Register a hook as `bash ~/.claude/hooks/claim-evidence-guard.sh` and Windows
resolves `bash` against `PATH`, where `C:\Windows\System32\bash.exe` usually
comes first. That is the WSL launcher. Inside WSL:

```
$ bash -c 'echo $HOME; ls ~/.claude/hooks/'
/home/<you>
ls: cannot access '/home/<you>/.claude/hooks/': No such file or directory
```

Different home directory, different filesystem. The script is sitting in
`C:\Users\<you>\.claude\hooks\`, which that `~` does not point at. The hook
never runs.

Git Bash is fine -- it just has to be named explicitly, by full path:
`"C:\Program Files\Git\bin\bash.exe"`.

### 3. `chmod +x`, `which jq`, `brew install jq`

None of these apply. Windows has no execute bit, and no `brew`.

---

## The Windows build

Each hook has a `windows/` folder next to `claude-code/` and `codex/`:

```
hooks/claim-guard/windows/claim_ledger_tracker.py
hooks/claim-guard/windows/claim_evidence_guard.py
hooks/lint-gate/windows/lint_gate.py
hooks/no-emoji-guard/claude-code/no-emoji-guard.py   (already Python, works as-is)
hooks/test-gate-guard/claude-code/test_gate_guard.py (Python, works everywhere)
```

The judging logic is unchanged from the shell versions -- same triggers, same
fail-open rules, same messages. What changed is the plumbing:

| | Shell build | Windows build |
|---|---|---|
| Parses input with | `jq` | Python standard library |
| Runs under | `bash` | `python` |
| lint-gate settings | `VAR=value` prefix (POSIX shells only) | `--cmd` / `--fail` arguments, which mean the same thing in cmd, PowerShell, and Git Bash |
| Extra dependencies | `jq` | none |

Both builds use the same ledger directory (`%USERPROFILE%\.cache\claude-guard-hooks`),
so switching from one to the other needs no cleanup.

---

## Install

**1. Check Python is there.** In PowerShell:

```powershell
python --version
```

Anything 3.8 or newer is fine. If that prints nothing useful, install Python
from python.org and reopen the terminal.

**2. Copy the hooks in.** Flat into `%USERPROFILE%\.claude\hooks\` -- do not
keep the folder structure from this repo:

```powershell
$dst = "$env:USERPROFILE\.claude\hooks"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item hooks\claim-guard\windows\*.py $dst
Copy-Item hooks\lint-gate\windows\lint_gate.py $dst
Copy-Item hooks\no-emoji-guard\claude-code\no-emoji-guard.py $dst
Copy-Item hooks\test-gate-guard\claude-code\test_gate_guard.py $dst
```

No `chmod` step. Windows does not have one.

**3. Register them.** Merge the blocks you want from
[`settings-example.windows.json`](../settings-example.windows.json) into
`%USERPROFILE%\.claude\settings.json`.

Two things that go wrong here more than anything else:

- Your `settings.json` almost certainly has content already. **Merge**, do not
  overwrite. Back it up first.
- Write **full absolute paths**, not `~`. Whether `~` expands depends on which
  shell ends up running the command, and that is exactly the ambiguity this
  page is about.

**4. Restart Claude Code completely.** Hooks load at startup. Until you have
quit and reopened, nothing you just did is in effect.

**5. Prove it, do not assume it.**

```powershell
python scripts\verify-install.py
```

That script does not read your config and pronounce it fine. It fires each
installed hook with a synthetic payload and checks the answer: that
claim-guard blocks "tests pass" on an empty ledger and allows it once a real
test run is on record, that lint-gate blocks a failing check and still lets a
second pass through, that test-gate-guard blocks `pytest ; git push` and
allows `pytest && git push`. It also flags a bare `bash` command or a missing
`jq` in your settings.

Exit code 0 means every installed piece answered correctly.

---

## If you would rather keep the shell versions

That works, with two conditions:

1. Install `jq`: `winget install jqlang.jq`, then reopen the terminal.
2. Register with the full Git Bash path, never a bare `bash`:

```json
"command": "\"C:\\Program Files\\Git\\bin\\bash.exe\" \"C:\\Users\\<you>\\.claude\\hooks\\claim-evidence-guard.sh\""
```

Then run `python scripts\verify-install.py` and confirm it comes back clean.
The point stands either way: a hook you have not seen fire is a hook you do not
know is installed.
