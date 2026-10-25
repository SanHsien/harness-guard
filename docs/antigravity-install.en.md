# Google Antigravity (AGY) Installation & Integration Guide

> English | [繁體中文](antigravity-install.md)

Google Antigravity (AGY) provides a powerful Customization System encompassing Rules, Skills, Hooks, and Plugins. This guide details how to integrate `harness-guard` into your Antigravity environment.

---

## Quick Install (One Command)

Run in your terminal:

```bash
# Preview what will be installed
python scripts/install.py --agent antigravity --dry-run --skills all

# Install all skills into ~/.gemini/config/skills/
python scripts/install.py --agent antigravity --skills all
```

This copies the complete skill packages into the Antigravity global skills directory (`~/.gemini/config/skills/`), which Antigravity automatically discovers and loads via Progressive Disclosure.

---

## Hooks (optional)

Antigravity's `PreToolUse` hook fires before a tool runs and can answer `{"decision": "deny"}` to block it; its `Stop` hook fires when the execution loop ends and can answer `{"decision": "continue"}` to refuse the stop and send the agent back (official reference: `agy-customizations/docs/hooks.md`, bundled with `agy`). So guard hooks have a real interception point here. This repo ships Antigravity registrations for six optional hooks:

```bash
# preview (writes nothing)
python scripts/install.py --dry-run --agent antigravity --hooks danger-zone-guard,test-gate-guard,no-emoji-guard,claim-guard,lint-gate
# install
python scripts/install.py --agent antigravity --hooks danger-zone-guard,test-gate-guard,no-emoji-guard,claim-guard,lint-gate
# anti-doom-loop-guard is separate; --hooks all means all six
python scripts/install.py --agent antigravity --hooks anti-doom-loop-guard
```

### What each hook does in Antigravity

Tool names are the lowercased step types. Every hook is the **same script** as its Claude Code build and recognises Antigravity by Antigravity's own fields (`toolCall`, `conversationId`); Claude, Codex and Cursor behave exactly as before.

| Hook | Event | Matcher | Mechanism | Notes |
|---|---|---|---|---|
| `danger-zone-guard` | `PreToolUse` | `run_command` | deny | reads `toolCall.args.CommandLine`; same rules as the Claude build |
| `test-gate-guard` | `PreToolUse` | `run_command` | deny | same: `pytest ; git push` is blocked, `&&` passes |
| `no-emoji-guard` | `PreToolUse` | `write_to_file\|replace_file_content\|multi_replace_file_content` | deny | scans `CodeContent`, `ReplacementContent` and `ReplacementChunks[].ReplacementContent`; the path is `TargetFile`; `no-emoji-guard.json` sits beside the script |
| `claim-guard` (ledger) | `PostToolUse` | `run_command\|grep_search\|find_by_name\|list_dir\|write_to_file\|replace_file_content\|multi_replace_file_content` | records only, answers `{}` | notes which verification commands ran, which searches happened and which files were edited (an edit after the last verification makes that verification stale for the check); a call with a non-empty `error` (the tool failed) is not recorded, so a failed test run is not evidence |
| `claim-guard` (check) | `Stop` | none (Stop takes no matcher) | continue | see limit 1 below: **it can block, but how it gets the message is not guaranteed by the official docs** |
| `lint-gate` | `Stop` | none | continue | runs only when the project root (`workspacePaths[0]`) has a `.lint-gate.json`; on failure the output goes back to the agent |
| `anti-doom-loop-guard` | `PreToolUse` | `run_command\|view_file\|write_to_file\|replace_file_content\|multi_replace_file_content` | deny | denies the same `run_command` or `view_file` three times in a row with no other tool call in between; edit tools reset the count |

| Output | Format |
|---|---|
| Deny (`PreToolUse`) | stdout `{"decision":"deny","reason":"..."}`, exit 0 |
| Refuse the stop (`Stop`) | stdout `{"decision":"continue","reason":"..."}`, exit 0 |
| Allow | `PreToolUse` answers `{"decision":"ask"}`, handing the call to Antigravity's normal permission flow (`decision` is required: an empty `{}` is read as a deny with an empty reason, which blocks every command); it never answers `allow`, which auto-approves and skips a prompt you still want |

> Before this release `danger-zone-guard`, `test-gate-guard` and `no-emoji-guard` answered `{"decision":"allow"}` to Antigravity on an allow; they now answer `{"decision":"ask"}` (a short-lived `{}` blocked every `run_command`; fixed).

### Registration layout

In `~/.gemini/config/hooks.json` the **top-level key is the hook's name** with its events underneath, unlike Claude Code's nested `hooks` block. The two kinds of event have different shapes:

```json
{
  "danger-zone-guard": {
    "PreToolUse": [
      { "matcher": "run_command",
        "hooks": [ { "type": "command", "command": "python C:\\Users\\<you>\\.gemini\\config\\hooks\\danger_zone_guard.py", "timeout": 10 } ] }
    ]
  },
  "lint-gate": {
    "Stop": [
      { "type": "command", "command": "python C:\\Users\\<you>\\.gemini\\config\\hooks\\lint_gate.py", "timeout": 60 }
    ]
  }
}
```

`PreToolUse` / `PostToolUse` use `{matcher, hooks:[...]}` groups; `Stop` is a **flat** list of handlers, with no matcher and no `hooks` wrapper. Writing `Stop` as a group (Claude Code's shape) is a likely reason the old Claude-layout file was rejected as a whole (`invalid hook "hooks": command hook must specify 'command'`).

| Item | Detail |
|---|---|
| Scripts | `~/.gemini/config/hooks/` (flat; hooks never import each other) |
| Backup | backed up to `~/.gemini/backups/hooks.json.bak-<time>` first; read back after writing; re-running does not duplicate |
| Merge | adds only its own entries; every other hook name and your own content stays as it was; an existing registration of the same script (for example a hand-added `anti-doom-loop-guard`) counts as installed and is not duplicated |
| Refuses to write | when the file has a Claude Code layout top-level `hooks` block, or any entry in a shape Antigravity would reject (for example `Stop` wrapped in a matcher group), the installer prints `REFUSED` and the reason and **copies nothing, backs nothing up, writes nothing**: Antigravity rejects the file as a whole, so writing into it would report an install whose hooks never run. Move that block out of the file (keep a backup) and run it again |
| Without `--hooks` | Antigravity gets skills only |

**No quotes in the command, and no whitespace in the path.** Antigravity's bundled reference says the command runs through `cmd /c` (Windows) or `sh -c`, but at least one build splits argv itself and handles no quotes; no quotes and no whitespace work under both readings. So the installer writes commands like `python C:\Users\<you>\.gemini\config\hooks\anti_doom_loop_guard.py`. If the path has whitespace or a quote the installer refuses and says why; pass `--gemini-dir` with a path that has none.

### Limits and what is not done

1. **`claim-guard`'s check cannot see the assistant message.** The `Stop` payload carries `conversationId`, `transcriptPath`, `terminationReason` and so on, but not the last message, so the script reads the file `transcriptPath` points to. The official hooks reference does not describe that file's line format; the script follows the step shape the `run-workflow` reference documents (`type: PLANNER_RESPONSE`, `text`) and lets the turn end when it finds no model message (fail-open), so a different format makes it do nothing rather than block wrongly. `verify-install.py` checks it against a synthetic transcript of that shape: that proves the adapter logic, **not that a real transcript is readable**. See it block once in a real session before you rely on it.
2. **`Stop` has no `stop_hook_active`.** Claude Code uses it to avoid blocking forever; Antigravity has no such flag, so `claim-guard` and `lint-gate` keep a fingerprint of "this message / this failure output was already blocked once" (in the temp directory; `HARNESS_GUARD_STATE_DIR` moves it): the agent trying again unchanged is let through, a changed message or failure blocks again, and a clean pass forgets it.
3. They check only when `terminationReason` is `NO_TOOL_CALL` or `TERMINAL_STEP_TYPE` (a normal finish); a user cancel, an error or a limit is let through.
4. Apart from `run_command.CommandLine`, the tool argument names (`TargetFile`, `CodeContent`, `ReplacementContent`, `ReplacementChunks`) are not listed in the official hooks reference; they follow what this repo's `no-emoji-guard` already did for Antigravity, so trust a real run.
5. The official reference does not list `view_file`'s argument names; `anti-doom-loop-guard` uses the whole argument object as its signature and depends on no particular name.
6. **herdr's `herdr-agent-state.ps1` is not covered**: it is herdr's own integration and uses events Antigravity does not have (`UserPromptSubmit`, `Notification`, `SessionEnd`, ...). This installer neither handles nor touches it.
7. `fork_pr_guard` is not in this repo (it is the maintainer's own hook), so nothing registers it here.

---

## Rules Integration (GEMINI.md)

Antigravity supports hierarchical rule resolution (Global: `~/.gemini/GEMINI.md`, Project: `GEMINI.md` or `.agents/rules/*.md` in repo root).

1. Review `gemini-md-template/GEMINI.md` in this repository.
2. Merge its guidelines into your `~/.gemini/GEMINI.md` or your project root.
3. Modular rules from `gemini-md-template/rules/` can be copied into `.agents/rules/` or `~/.gemini/config/rules/`.

---

## Trusted workspaces and auto-approve

To stop permission prompts interrupting you, edit `~/.gemini/antigravity-cli/settings.json`.

**Be clear about the trade.** Turning off prompts removes the human confirmation step, which
leaves these hooks as the only thing between the agent and your files. That is what this kit is
for — but it is an interceptor, not a sandbox. It blocks a known set of catastrophic commands,
not everything bad. The wider the scope, the larger the risk.

Trust **the folder your projects live in**, not your whole home directory. Your home holds SSH
keys, browser data, credentials, and every personal file you own; none of it belongs here:

```json
"trustedWorkspaces": [
  "C:\\Users\\<your-username>\\Documents\\GitHub"
]
```

Enable automation in two stages. First the parts that change nothing:

```json
"agent_features": {
  "auto_run_tests": true,
  "smart_context_retrieval": true,
  "web_search_enabled": true,
  "browser_testing_enabled": true,
  "mcp_enabled": true
}
```

Only once you have seen the hooks actually block something — `verify-install.py` green, and a
real block with your own eyes — consider the last three. With these on, file edits and command
execution no longer wait for a human:

```json
"auto_approve_commands": true,
"auto_approve_file_edits": true,
"skip_permission_prompts": true,
"auto_execution_mode": "full_auto"
```

---

## Verify Installation

Run self-verification:

```bash
python scripts/verify-install.py --agent antigravity
```

For every hook from this repo that is registered in `hooks.json`, it checks the registration (no Claude-layout top-level `hooks` block, `Stop` as a flat list, no quotes, a matcher that covers the tools the hook looks at, the script exists) and then live-fires Antigravity-shaped payloads, one allow and one block:

- `danger-zone-guard`: `rm -rf /` is denied, `rm -rf dist/` answers ask; `test-gate-guard`: `pytest ; git push` is denied, `&&` answers ask;
- `no-emoji-guard`: a `write_to_file` with emoji is denied, clean content answers ask;
- `claim-guard`: with an empty ledger `Stop` answers continue, after one `pytest -q` was recorded the same claim passes (the transcript is synthetic, see limit 1 above);
- `lint-gate`: a project with no `.lint-gate.json` answers `{}`, a failing check answers continue, the identical failure passes the second time;
- `anti-doom-loop-guard`: an edit in between does not block, three identical commands in a row do.
