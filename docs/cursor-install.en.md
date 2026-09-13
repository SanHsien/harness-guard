> English | [中文版](cursor-install.md)

# Installing on Cursor

Cursor's hook contract is not Claude Code's. Pasting a Claude Code `settings.json` block into Cursor does nothing. This page is only the differences; the shared install contract is still [`../AGENTS.md`](../AGENTS.md) and `scripts/install.py`.

## Why the Claude Code config file cannot be reused

| | Claude Code | Cursor |
|---|---|---|
| Config | nested `hooks[].hooks[]` in `~/.claude/settings.json` | flat `~/.cursor/hooks.json` with top-level `"version": 1` |
| Block shell | `PreToolUse` + matcher `Bash`, `exit 2` | `beforeShellExecution`, stdout `{"permission":"deny"}` (`exit 2` also works) |
| Block writes | `PreToolUse` + matcher `Write\|Edit\|MultiEdit` | `preToolUse` + matcher `Write` |
| End of turn | `Stop` can `{"decision":"block"}` | `stop` **cannot veto**; it can only send `followup_message` |
| User-level cwd | usually the project directory | `~/.cursor/` |

Cursor can also load Claude Code third-party hooks if that setting is enabled, but the payload may still be Cursor-shaped. This installer writes native Cursor format and does not depend on that toggle.

## Install

```bash
python scripts/install.py --dry-run --agent cursor --hooks all --skills all
python scripts/install.py --agent cursor --hooks all --skills all
```

The installer:

1. copies Python hooks flat into `~/.cursor/hooks/`;
2. **merges** into `~/.cursor/hooks.json` (after a backup); re-running does not duplicate;
3. copies skills into `~/.cursor/skills/`. If `~/.agents/skills/` already exists, it is merged too. Same-name folders are left alone.

On Windows the `command` is `python "C:\Users\<you>\.cursor\hooks\....py"`. No shebang, no relative path. A relative path might resolve from the user-hook cwd, but Windows will not pick an interpreter from a shebang.

## Event mapping

| Guard | Cursor event | Can it block? |
|---|---|---|
| test-gate-guard | `beforeShellExecution` | yes; top-level `command` |
| danger-zone-guard | `beforeShellExecution` | yes |
| no-emoji-guard | `preToolUse` (matcher `Write`) | yes, via `permission: deny` |
| claim-ledger-tracker | `postToolUse` | record only |
| claim-evidence-guard | `stop` | **no veto**. Sends `followup_message` when a completion claim has no evidence |
| lint-gate | `stop` | same; project directory comes from payload `cwd` / `workspace_roots`, not `~/.cursor` |

If there is no `last_assistant_message`, claim-evidence-guard still fails open. That is the existing contract, not a Cursor-only relaxation: unreadable input is never a reason to get in the way.

## Verify

```bash
python scripts/verify-install.py --agent cursor
```

It feeds Cursor-shaped payloads into the copied scripts. A config file that looks right is not evidence. If the live-fire does not block, it is not installed.

Cursor usually reloads `hooks.json` on save. If the Hooks output channel does not show the new hooks, restart the window.
