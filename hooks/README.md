# Five interceptor hooks, in up to three builds each

Each one has its builds in folders underneath it:

```
hooks/<tool-name>/
├── claude-code/   for Claude Code
├── codex/         for Codex
└── windows/       Python build, no jq, no bash (pure Python, cross-platform)
```

The fourth and fifth hooks (`test-gate-guard/` and `danger-zone-guard/`) are added by this fork.
They are pure Python on all platforms and require no external dependencies.

`checkout-guard/` (also added by this fork, Claude Code build, pure Python) stops two
agents from editing the same file at once. It is a PreToolUse hook on `Edit|Write|MultiEdit|NotebookEdit`
that reads the check-out locks [agent-relay](https://github.com/SanHsien/agent-relay)
keeps in its store (SPEC section 9). If the file is checked out by someone else it
exits 2 and names the holder; every decision is appended to
`~/.agent-relay/touch-log.jsonl`. Without agent-relay set up it allows everything.
Register it like the others, with matcher `Edit|Write|MultiEdit|NotebookEdit`:
`python "C:\Users\<you>\...\harness-guard\hooks\checkout-guard\claude-code\checkout_guard.py"`.

`anti-doom-loop-guard/` (also added by this fork, optional, not one of the five) blocks the same
Bash or Read call issued three times in a row with no other tool call in between. It is **one self-contained
file for all four agents**, `claude-code/anti_doom_loop_guard.py`: hooks are installed flat and may not import
each other, so the shared core (signature, state, threshold, audit log) and the thin per-agent adapters live
together. Only the two ends differ:

| Agent | Event | Identified by | Deny |
|---|---|---|---|
| Claude Code | `PreToolUse`, matcher `Bash\|PowerShell\|Read\|Edit\|Write\|MultiEdit\|NotebookEdit` | `tool_name` | exit 2, reason on stderr |
| Codex | `PreToolUse`, matcher `exec\|shell\|exec_command\|shell_command\|Bash\|apply_patch\|Write\|Edit\|MultiEdit` | `--agent codex` (its payload looks like Claude's) | `{"decision":"block","reason":...}`, exit 0 |
| Cursor | `preToolUse`, matcher `Shell\|Read\|Write\|Delete` (`beforeShellExecution` / `afterFileEdit` also understood) | camelCase `hook_event_name` or `cursor_version` | `{"permission":"deny",...}`, exit 0 |
| Antigravity | `PreToolUse`, matcher `run_command\|view_file\|write_to_file\|replace_file_content\|multi_replace_file_content` | `toolCall` object | `{"decision":"deny","reason":...}`, exit 0 |

`--agent <claude|codex|cursor|antigravity>` overrides detection. Any other tool call resets the count, errors and
unknown events fail open, and `ANTI_DOOM_LOOP_THRESHOLD` changes the threshold. Tests:
`python hooks/anti-doom-loop-guard/tests/run-tests.py`. Install only this hook with
`python scripts/install.py --agent <claude|codex|cursor|antigravity> --hooks anti-doom-loop-guard`.

**Antigravity adapters for the other guards.** `danger-zone-guard`, `test-gate-guard`, `no-emoji-guard`,
`claim-guard` and `lint-gate` recognise Antigravity by `toolCall` / `conversationId` (never by a field other agents
also send) and answer in its contract: `PreToolUse` deny `{"decision":"deny","reason":...}`, `Stop` refuse
`{"decision":"continue","reason":...}`, allow `{}` (never `{"decision":"allow"}`, which auto-approves). Registered
with `install.py --agent antigravity --hooks <name>`; matchers and limits (notably: the `Stop` payload has no
assistant message, so `claim-guard` reads `transcriptPath`, whose format is not in the official docs) are in
[`../docs/antigravity-install.en.md`](../docs/antigravity-install.en.md). Tests:
`python hooks/tests/run-antigravity-tests.py`.

`danger-zone-guard/` blocks catastrophic deletions, force pushes to a protected
branch, and credential exfiltration. The force-push rule -- and only that rule --
has an escape hatch: put `# force-push-ok: <reason>` in the command. Squashing a
repository's history is a real request, and a gate with no way through pushes
people toward `git push origin +main` or the REST refs API instead, neither of
which this guard can see. The marker requires a written reason, and it does not
rescue a deletion or an exfiltration attempt: there is no legitimate `rm -rf /`.

**On Windows, use the `windows/` build.** The shell builds parse their input
with `jq`, which is not present on a stock Windows box, and without `jq` they
exit 0 -- which means "allow." Read [`../docs/windows-install.md`](../docs/windows-install.md)
(English: [`../docs/windows-install.en.md`](../docs/windows-install.en.md))
before registering anything there.

**The logic is identical on both sides.** What gets blocked, what gets let through, how evidence gets counted — it's the same set of rules. The only difference is the handful of lines tied to each platform's interface.

Install whichever one matches the tool you use. If you use both, install both — the ledger directories are kept separate (`~/.cache/claude-guard-hooks` and `~/.cache/codex-guard-hooks`), so they won't interfere with each other.

## How to configure it

- Claude Code → merge into `~/.claude/settings.json`; the example is `settings-example.json` at the repo root
- Codex → `install.py --agent codex` merges into `~/.codex/hooks.json` (example: `codex-hooks-example.json`); `~/.codex/config.toml` also needs `hooks = true`
- Cursor → `install.py --agent cursor` writes a flat `~/.cursor/hooks.json`; see [`../docs/cursor-install.md`](../docs/cursor-install.md)

## Where the two actually differ

The event names are **the same** (`PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `UserPromptSubmit`), and the `matcher` + `hooks` structure is the same too. The real differences come down to the five points below — use this table if you're porting another hook.

| | Claude Code | Codex |
|---|---|---|
| Where config lives | the `hooks` block in `settings.json` | a separate `~/.codex/hooks.json`, and `config.toml` needs `hooks = true` |
| This turn's identifier | `session_id` | **`turn_id`** (safest to write `.turn_id // .session_id` and try both) |
| Tool names in the matcher | `Write`/`Edit`/`MultiEdit`/`Bash`/`WebFetch` | editing a file is `apply_patch`, running a command is `exec`/`shell`/`exec_command`, fetching a page is `web_fetch` |
| Project directory | env var `CLAUDE_PROJECT_DIR` | doesn't exist — read `cwd` from the payload instead |
| What to output when allowing something | just exit quietly | **print `{}`** — printing nothing gets treated as an anomaly |
| How to express a block | `exit 2` + a message to stderr | print `{"decision":"block","reason":"..."}` |
| Trust mechanism | none | a hook has to be trusted before it runs; the first activation needs confirmation |

Codex also has `PostCompact`; Claude Code has `PreCompact`, `SessionEnd`, and `Notification`. Each side has events the other doesn't — check that the one you want actually exists before you wire it up.

`stop_hook_active`, `last_assistant_message`, `tool_name`, and `tool_input` share the same field names on both sides, so you can reuse those directly.

## Porting another hook yourself

The table above is the whole story. The core logic doesn't need to change — `claim-ledger-tracker`, excluding comments, is 26 lines in one version and 32 in the other; the extra six lines are all defensive checks like "skip if `jq` isn't available." The comparison expression that actually does the judging hasn't changed by a single character.

**After porting, always trigger it once for real to confirm it actually fires.** Don't assume it's working just because it didn't error — that's exactly the failure mode these three tools exist to catch.
