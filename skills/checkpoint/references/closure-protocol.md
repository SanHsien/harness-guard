# Checkpoint Closure Protocol

The input is a closure manifest produced by the main thread. You are the sole closure worker; don't spawn further subagents, and don't re-summarize the whole conversation.

## 1. Re-verify state

1. Confirm the manifest's date and timezone with `date`.
2. Re-run status/branch checks per repo; don't process the same vault path twice.
3. Treat dirty files not listed in the manifest as concurrent or someone else's changes; read the diff to judge attribution — if you can't safely separate them, leave them in place and flag a warning.
4. Check coverage: every changed file, and every listed external / scheduled / payment / todo action, must be classified. If you find a gap, stop and send it back to the main thread to fill in the manifest — don't guess.

## 2. Write the daily log exactly once

Except for `git-only`, `daily_action: skip_duplicate`, or no material session, read:

Write it once following your own log-format conventions (if you have a separate logging process script, read its conventions file, but don't run the whole thing — that would duplicate the work). Use the `daily_entries` from the manifest for the content. Don't write a second entry during the reconciliation step in the same pass.

## 3. Conditional fact reconciliation

- `git-only`: skip.
- `scoped` with an empty fact list: skip, report `sync: skipped (no fact delta)`.
- Otherwise: read `<neat-freak-skill-dir>/references/sync-protocol.md` in full, passing it the manifest's mode, memory_mode, fact list, and paths.

The sync protocol only reconciles facts — it does not commit. Move to the next section once it's done.

## 4. Verify, stage, commit, push

For each repo:

1. Read status and diff to confirm attributable files; exclude `.env`, `credentials*`, `*.secret`, session dumps, lock files, and any sensitive data not authorized by the manifest.
2. Run tests proportionate to the risk of the change; at minimum `git diff --check`. If the repo has its own lint/check scripts, run those too — fixes stay scoped to what's relevant to this closure, not a full periodic-maintenance sweep.
3. Stage file by file — never a blind `git add -A`. Scan the staged diff for secret-like patterns, but don't print the matched values.
4. If the staged diff is empty, report clean — don't create an empty commit.
5. Conventional Commit subject ≤72 characters; only add `Co-Authored-By` when the system or user explicitly asked for it.
6. Push the current branch; report failures honestly, no force push.
7. Verify local `HEAD == origin/<branch>`. If you need live-remote evidence and network access is available, also compare against `git ls-remote`.

When the vault and the current repo differ, commit each separately; only include files attributable to this session. If they overlap and can't be separated, stop on that repo rather than sweeping unknown changes in.

## 5. Report back

```text
daily: written | skipped (<reason>)
sync: skipped | scoped | full (<gate summary>)
repos:
- <path> <hash|clean> pushed=<branch|no>
preserved:
- <unrelated dirty file>
warnings:
- <item>
```

Attach the final enumerate evidence once; don't repost the full diff or the protocol text.
