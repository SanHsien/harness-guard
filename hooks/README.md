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
