---
name: checkpoint
description: "Close a session once: daily log, optional fact sync, selective commit/push, and remote verification. Use for /checkpoint, end of session, save, push, commit and push, or checkpoint + neat-freak."
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Agent Read
---

# Checkpoint — the single closure entry point

`checkpoint` is the public closure entry point; `neat-freak` is the fact-reconciliation engine it can optionally call. When both are named at once, run exactly one closure flow — don't summarize, delegate, write the daily log, or verify twice.

## Modes

- `scoped` (default): write the daily log once; run a targeted reconciliation only if there's a fact list, then commit + push.
- `full`: the user explicitly named `neat-freak`, knowledge sync, memory cleanup, or a full closure — run the complete GATE reconciliation before commit + push.
- `git-only`: only when the user explicitly says no log / no sync.

## 1. The main thread builds the closure manifest exactly once

Use the current platform's task/plan mechanism to build one closure plan; don't build a second one for neat-freak.

1. Get the date and timezone with `date`.
2. Check `git status --porcelain`, `git diff --stat HEAD`, and the current branch for the current repo (and any other project roots listed in the manifest).
3. Review the whole conversation once, producing:
   - `session_summary`: 0–3 items each of what was completed / decided / any pitfalls hit.
   - `fact_list`: facts that changed → the files they affect; not just a list of touched files.
   - `daily_entries`: the condensed content to write into the daily log.
   - `repos`: repo, branch, attributable files, tests run.
   - `coverage`: every changed file, and every external action / scheduled item / payment / todo change, must be tagged `fact_delta: yes` (linked to the fact list) or `fact_delta: no` (with a one-line reason). Anything left unclassified blocks delegation.
4. Compare against today's daily log, recent commits, and the current file state; if another session already wrote the same content more recently, mark `daily_action: skip_duplicate` — don't duplicate or backfill it.
5. The manifest must include `mode`, `memory_mode`, the folder for whichever process scripts are currently in use, the memory folder, the knowledge base root, and every project folder being closed out.

`memory_mode` defaults to `read-only`; it's only `update` when the user explicitly asked for neat-freak, memory sync, or memory cleanup.

## 2. Execute exactly once

Hand the manifest to a fresh-context, general-purpose bounded subagent:

- Codex: use `fork_turns: "none"`, prompt carries only the manifest and this file's path.
- Claude Code: use a fresh general-purpose Agent/Task subagent with `model: sonnet`; it won't see the main thread's conversation history but still loads applicable CLAUDE.md / permissions. The delegation prompt carries only the manifest and this file's path.

The first instruction must tell it to read `references/closure-protocol.md` in full, not spawn any further subagents, and not separately invoke neat-freak. If the platform has no subagent support, or the task is a single-repo `git-only`, the main thread follows that protocol directly.

## 3. Main-thread verification

A subagent's report is a claim, not a fact:

1. If sync edits were made, spot-read 1–2 of the files it claims to have changed.
2. Confirm each item appears in the daily log exactly once.
3. Per repo, check the reported hash, `git log -1 --oneline`, and `HEAD == origin/<current-branch>`.
4. Recheck `git status --short`: changes attributable to this session should be closed out; unrelated or concurrent changes should be left untouched and listed.

## Condensed report

```text
daily: written | skipped (<reason>)
sync: skipped | scoped | full (<GATE result>)
commit: <repo> <hash> | clean
vault: <hash> | clean | preserved unrelated changes
pushed: <branches>
warnings: none | <items>
```

No force push; no blind `git add -A`; never sweep unattributable changes in just to make things look clean.
