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

Antigravity's `PreToolUse` hook fires before a tool runs and can answer `{"decision": "deny"}` to block it, so guard hooks have a real interception point here (official reference: `agy-customizations/docs/hooks.md`, bundled with `agy`). This repo ships one Antigravity registration so far:

```bash
python scripts/install.py --dry-run --agent antigravity --hooks anti-doom-loop-guard
python scripts/install.py --agent antigravity --hooks anti-doom-loop-guard
```

| Item | Detail |
|---|---|
| Script | `~/.gemini/config/hooks/anti_doom_loop_guard.py` |
| Registration | `~/.gemini/config/hooks.json`; the **top-level key is the hook's name** (`anti-doom-loop-guard`) with its events underneath, unlike Claude Code's nested `hooks` block |
| Event / matcher | `PreToolUse`, `run_command\|view_file\|write_to_file\|replace_file_content\|multi_replace_file_content` (tool names are the lowercased step types) |
| Behaviour | denies the same `run_command` or `view_file` three times in a row with no other tool call in between; edit tools reset the count |
| Deny format | stdout `{"decision":"deny","reason":"..."}`, exit 0 |
| Allow format | stdout `{}`. It does not answer `{"decision":"allow"}`: in Antigravity `allow` means "approve this call automatically", which would skip a permission prompt you still want |
| Backup | backed up to `~/.gemini/backups/hooks.json.bak-<time>` first; read back after writing; re-running does not duplicate |

The installer adds only its own entry and keeps every other hook name and your own content as it was. Without `--hooks`, Antigravity gets skills only; `--hooks all` installs only hooks that have an Antigravity registration, and any other name prints a note and is skipped.

**No quotes in the command, and no whitespace in the path.** Antigravity's bundled reference says the command runs through `cmd /c` (Windows) or `sh -c`, but at least one build splits argv itself and handles no quotes; no quotes and no whitespace work under both readings. So the installer writes `python C:\Users\<you>\.gemini\config\hooks\anti_doom_loop_guard.py`. If the path has whitespace or a quote the installer refuses and says why; pass `--gemini-dir` with a path that has none.

Known limits:

- The official reference does not list `view_file`'s argument names; the script uses the whole argument object as the signature, so it never depends on a particular name and does not mistake paging for a retry.
- The other five hooks (claim-guard, test-gate-guard, danger-zone-guard, lint-gate, no-emoji-guard) have no Antigravity registration yet, and the installer writes nothing to `hooks.json` for them.
- If your `hooks.json` already has a top-level `hooks` block in Claude Code's layout, the installer warns and leaves it alone; one Antigravity build reported `invalid hook "hooks"` for such a file, so trust what `agy` actually loads.

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

When `anti-doom-loop-guard` is registered, it checks the registration (no quotes, matcher) and live-fires an Antigravity-shaped payload: an edit in between does not block, three identical commands in a row do.
