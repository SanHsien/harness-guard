> English | [中文版](CHANGELOG.md)

# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), newest first.
Entries marked `fork` are this fork's changes relative to
[upstream](https://github.com/agentcrew-academy/harness-starter-kit).

---

## 2026-10-26

### Fixed

- `fork` test-gate-guard: chains that mix `&&` and `;` (`pytest && echo ok ; git commit`, `pytest ; ls && git push`) were let through because an `&&` appeared anywhere between, so a red test still committed. Any `;` or newline between the test and the `git commit`/`push` now blocks. Git options before the subcommand (`git -C path push`, `git -c k=v commit`, `git --no-pager push`) were invisible and are now matched. A `<<<` here-string is no longer read as a heredoc that swallows the rest of the command, and an escaped quote (`\"`) no longer throws quote pairing off. A newline after a trailing `&&`, `||` or `\` continues the command and is not flagged.
- `fork` danger-zone-guard: force-push detection now inspects each `git push` command's arguments instead of requiring the flag right after `push`. `git push origin main --force`, `git -C repo push -f origin main`, `git push origin +main` and `git push --force origin "main"` used to slip through; `git push -f origin feature/release-notes` (a branch merely containing "release") and `git push -f origin feat; echo main` (main belongs to another command) were wrongly blocked and are now allowed.

## 2026-10-25

### Fixed

- **Upstream checker `check_upstream_updates.py`: a check that could not run always exits 2 (`fork`).** A missing
  `gh`, `gh` output of the wrong shape, an unwritable report, a console encoding error or a broken stdout used to
  end in a traceback with exit 1, which `--strict` callers read as "unreviewed commits". All of them now write
  "Check failed" / "Not checked" and exit 2; a rewritten upstream history is reported as rewritten and a shallow
  clone as shallow, instead of listing what looks like an ordinary run of new commits.
  The baseline is validated on load too: `reviewed_through` must be a full SHA, the PR/issue watermarks
  non-negative integers, and `repo` / `branch` may not start with `-` (git would read that as an option such as
  `--upload-pack=...`). A local upstream path may contain spaces (e.g. `C:\Program Files\up`); a branch name may
  not. The report is written with `errors="replace"`, so a lone surrogate in a title still leaves a report file.
- **Windows: Claude Code's PowerShell tool bypassed `danger-zone-guard` and `test-gate-guard` entirely (`fork`).**
  Both were registered for the `Bash` matcher only and the scripts only recognised `Bash`-style tool
  names, so `git push --force` or `pytest ; git push` run through the PowerShell tool went through, and
  `;` is PowerShell's usual separator. The matcher is now `Bash|PowerShell` and both scripts treat
  `PowerShell` as a shell tool; re-running `install.py` moves an old-matcher registration over.
- **Re-running the installer did not update a registration whose matcher changed (`fork`).** Once a
  script's exact command sat in any matcher group, the installer reported "already registered", so an
  install made before a hook's matcher widened (for instance `anti-doom-loop-guard` gaining the edit
  tools in c38bfd7, which lets an edit reset the count) never picked it up and the count still never
  reset. Claude Code, Codex, Cursor and Antigravity now count a hook as registered only under the same
  command and the same matcher; a registration of the same script under another matcher is removed and
  re-added under the current one (reported as `removed N outdated registration(s)`), and the user's own hooks in that group
  are left alone.
- **claim-guard: "tests pass" still counted as backed after more edits (ported from upstream e9a4734).**
  The tracker now records edits too (Claude `Write|Edit|MultiEdit|NotebookEdit`, Codex `apply_patch`,
  Cursor `Write|Delete`, Antigravity `write_to_file|replace_file_content|multi_replace_file_content`), and the
  check blocks once, naming both, when the last edit came after the last verification; the second pass
  (`stop_hook_active`) still lets it through. Both the shell and the Python builds.
- **claim-guard: mentioning a trigger phrase counted as making the claim (ported from upstream e9a4734).**
  Text inside 「」 or backticks is dropped before matching, so "I added `tests pass` to the trigger list"
  is no longer blocked. The shell builds use `jq`'s Unicode regex, so no locale is assumed.

### Added

- **claim-guard records more kinds of evidence (ported from upstream 7b0df03 / e9a4734)**: `WebSearch` /
  `WebFetch` (Codex's `web_fetch`) count as searches; `mcp__claude-in-chrome__*` and `playwright test` /
  `agent-browser` count as verification; on Windows, Claude Code's `PowerShell` tool is recorded like
  `Bash`. The installer's tracker matchers widen to match (Claude, Codex, Antigravity), a re-run of
  `install.py` moves an old-matcher registration over, and `verify-install.py` checks that the matcher
  covers the edit tools.

## 2026-10-23

### Fixed

- **Antigravity: every `run_command` was blocked (`fork`).** Antigravity reported
  `tool call denied by pre-tool hook: ` with nothing after the colon, even for
  `python -c "print('hello')"`. Cause: the official `PreToolUse` output requires `decision`, and
  `danger-zone-guard`, `test-gate-guard`, `no-emoji-guard` and `anti-doom-loop-guard` answered an allow
  with an empty `{}`, which is read as a deny. Fix: an allow now answers `{"decision":"ask"}`, handing
  the call to Antigravity's normal permission flow (it respects "Always Allow"); never `allow`, which
  auto-approves and skips the permission prompt. `PostToolUse` and an allowing `Stop` still answer `{}`
  (as documented). Existing installs: rerun `python scripts/install.py --agent antigravity --hooks <name>`;
  `verify-install.py` now checks that an allow answers ask.

### Added

- **`anti-doom-loop-guard` now covers Codex, Cursor and Antigravity and installs through the installer (`fork`).**
  It still blocks the same Bash or Read call issued three times in a row with no other tool call in
  between. One file holds the shared core (signature, state, threshold, audit log) and four thin
  per-agent adapters, because hooks are installed flat and may not import each other: Codex answers
  `{"decision":"block"}` (needs `--agent codex`; its payload resembles Claude's), Cursor runs on
  `preToolUse` (`Shell|Read|Write|Delete`) and answers `{"permission":"deny"}`, Antigravity runs on
  `PreToolUse` (`toolCall`) and answers `{"decision":"deny"}`. Cursor does not use `beforeReadFile`: it
  has no offset or limit, so paging through a big file would be misread as a retry. For Cursor and
  Antigravity reads, the whole tool-argument object is the signature rather than guessed field names.
- **`install.py --agent <claude|codex|cursor|antigravity> --hooks anti-doom-loop-guard` installs only this hook.**
  On Claude Code an existing manual install (same file name, a `PreToolUse` registration with that
  matcher; quoting, slash direction and case may differ) counts as already present and is not
  duplicated. Antigravity gets its first hook support: a named entry merged into
  `~/.gemini/config/hooks.json`, a command with no quotes, and a refusal when the path has whitespace;
  without `--hooks`, Antigravity still installs skills only. `--dry-run` now lists the files it would
  copy and merge.
- **`verify-install.py` live-fires `anti-doom-loop-guard` on all four agents**: an edit in between does
  not block, three identical commands in a row block in that agent's format; it also checks that the
  Antigravity command has no quotes and the Codex registration carries `--agent codex`.
- **Five guard hooks for Antigravity (`fork`): `danger-zone-guard`, `test-gate-guard`, `no-emoji-guard`,
  `claim-guard` and `lint-gate`.** Antigravity's `hooks.json` used to hold these in Claude Code's layout,
  was rejected as a whole, and none of them ever ran. Each is now a named hook in `hooks.json`:
  `PreToolUse` (`run_command`; `write_to_file|replace_file_content|multi_replace_file_content` for
  `no-emoji-guard`) denies with `{"decision":"deny"}`, `claim-guard`'s ledger runs on `PostToolUse`
  (`run_command|grep_search|find_by_name|list_dir`; a failed tool call is not recorded), its check and
  `lint-gate` run on `Stop` (a **flat** handler list, no matcher) and refuse the stop with
  `{"decision":"continue"}`, and every allow is `{}`. Same scripts, told apart by `toolCall` /
  `conversationId`; Claude, Codex and Cursor behave as before. `Stop` has no `stop_hook_active`, so the
  same message / the same failure is blocked only once. **Limit:** the `Stop` payload has no assistant
  message, so `claim-guard`'s check reads `transcriptPath`, whose line format the official docs do not
  give; it follows the step shape in the `run-workflow` docs and lets the turn end when it finds nothing.
  herdr's hook is out of scope. Details in `docs/antigravity-install.en.md`.
- **`install.py --agent antigravity --hooks <name>[,<name>...]` installs any combination of the six
  hooks** (`--hooks all` is all of them): named entries, backup first, read back after writing, no
  duplicates on re-run, an existing registration of the same script counts as installed.
  `verify-install.py --agent antigravity` checks the layout of every registered hook and live-fires one
  allow and one block. New `hooks/tests/run-antigravity-tests.py` (in CI).

### Changed

- `--hooks all` now also installs `anti-doom-loop-guard` (the default list is unchanged).
- After writing JSON configuration the installer now really reads it back and compares before
  printing "re-read and valid" (it printed that without reading before).
- **Antigravity: when `hooks.json` has a Claude Code layout top-level `hooks` block, or an entry in a shape
  Antigravity rejects (for example `Stop` wrapped in a matcher group), the installer now refuses to
  write** (prints `REFUSED` and the reason, copies and backs up nothing). It used to warn and write
  anyway, leaving a file Antigravity still rejected as a whole: hooks that never ran, reported as installed.

### Fixed

- The state file name contains the session id, which is now filtered to safe characters; an id with a
  `/` used to make the state write fail silently and leave the guard doing nothing.
- **`danger-zone-guard`, `test-gate-guard` and `no-emoji-guard` now answer `{}` to Antigravity on an allow**
  instead of `{"decision":"allow"}`: in Antigravity the latter means "approve this call automatically" and
  skips a permission prompt the user still wants.

## 2026-09-20

### Fixed

- **Machine evidence for completion claims now fails closed (`fork`).** An opted-in
  repository's Full summary must use schema v1, profile `full`, bind the current Git
  HEAD, and contain only boolean true gates. A second Stop pass no longer bypasses
  this check. Regression coverage is included in CI.
- **The danger-zone guard blocks unbounded Bash and PowerShell loops (`fork`).** A
  deliberately bounded exception can state `# bounded-loop-ok: <reason>`, while loop
  examples inside quoted text remain allowed.
- **Windows install verification now parses unquoted absolute Python hook paths
  correctly (`fork`).** Interpreter and script commands containing spaces are no
  longer misreported as missing hook files.

## 2026-08-24

### Fixed

- **The Codex claim tracker missed newer shell tool aliases (`fork`).** Newer
  Codex rollouts can record commands as `exec_command` or `shell_command`; the old
  Windows tracker accepted only `exec`, `shell`, and `Bash`, while the POSIX tracker
  accepted only `Bash`, so a command could run without producing a claim ledger.
  Both trackers and the installer hook matchers now accept the aliases and `cmd`
  payload, and `scripts/verify-install.py` requires installed matchers and tracker
  allowlists to cover them together.

- **`review-loop` also triggered for a one-pass final publication (`fork`).** Its
  frontmatter now activates only when a second feedback round exists or is explicitly
  planned. The final publication of that multi-round loop remains covered, while
  one-off replies and single-pass final drafts are excluded. Script commands now
  resolve relative to the current skill directory instead of another agent's install
  root.

## 2026-08-23

### Fixed

- **CI could not compile on Python 3.11: an f-string expression held a backslash
  (`fork`).** `render_ticket_section()` in `scripts/check_upstream_updates.py` did the
  escaping inside the f-string (`{ticket['title'].replace('|', '\\|')}`). That is legal
  from 3.12 on and a `SyntaxError` on 3.11, and the CI `compileall` matrix runs both
  3.11 and 3.14 -- the only local interpreter here is 3.14, so it looked fine while it
  was written and went red only in CI. The escape now happens outside the f-string, in
  a `title` local. Verified by running
  `python -m compileall scripts hooks skills/info-diet/scripts skills/review-loop/scripts`
  under uv's 3.11.15 for exit 0.

- **The Upstream check workflow handed `gh` no credentials, so it failed closed every
  run (`fork`).** The checker shells out to `gh pr list` / `gh issue list`, and `gh` in
  Actions cannot authenticate without `GH_TOKEN`. Both axes came back `None` and the
  checker failed closed by design (exit 2). The red run therefore read "could not
  enumerate upstream pull requests and issues", which looks like an upstream lookup
  problem and is actually a missing token. The workflow `env` now sets
  `GH_TOKEN: ${{ github.token }}`. Verified by running `--strict` locally with a token
  for exit 0.

### Added

- **A `# force-push-ok: <reason>` escape hatch for the force-push rule (`fork`).**
  `danger-zone-guard` blocked every force push to main/master with no way through.
  But "squash this repository's history" is a real request, and the force push *is*
  the operation that was asked for. A gate with no exit does not stop people; it
  pushes them toward `git push origin +main` or the REST refs API, neither of which
  this regex can see. Mirroring `fork_pr_guard`'s `# upstream-ok:`, the marker
  **requires a written reason** (a bare `# force-push-ok:` is still blocked) and
  applies **only to the force-push rule** -- it does not rescue `rm -rf /` or a
  credential exfiltration attempt. Both the claude-code and codex builds are
  updated, and `hooks/danger-zone-guard/tests/run-tests.py` pins all four
  properties.

## 2026-08-23

### Fixed

- **The upstream checker only looked at commits; pull requests and issues were never
  checked at all (`fork`).** Nothing read the `reviewed_pr_through` and
  `reviewed_issue_through` fields in `scripts/upstream_baseline.json`, yet the report
  still came out green -- and "checked, found nothing" and "never checked" look identical
  in a green report while only one of them is true. All three axes now get their own
  section, tickets are queried with `--state all` (an item opened and closed between two
  scheduled runs was still never triaged here), and an unavailable `gh` is reported as
  **Not checked** and fails the run closed (exit 2). `tests/test_upstream_check.py` pins
  that boundary with 12 cases: `None` (could not check) and `[]` (checked, nothing) must
  produce different report text and different exit codes.
- **What the first real check found**: PR #2 (read the payload as bytes for non-UTF-8
  locales) is merged and its merge commit is an ancestor of the watermark, and this fork's
  `no-emoji-guard.py:129` already carries the fix; issue #1 is a usage question. The
  watermarks move to PR #2 and issue #1, with the per-item reasoning in `FORK.md`.

## 2026-08-22

### Fixed

- **The installer no longer widens file permissions.** The CodeQL scan added today flagged four sites on its first run: hook files were written `0o755` (world-readable and world-executable), and the retry path for a skill folder that will not delete ran `chmod 0o777` (world-writable) first. These hooks are run by the user who installed them and by nobody else, so no other local account needs to read or execute them, and a delete needs only the owner's rwx. All four become `stat.S_IRWXU` (0o700). A guardrail kit should not be the thing that widens a permission.

### Added

- **`phantom-pushback` skill, adopted from upstream `3baf40e`.** It targets the closing paragraph where an AI invents a position you never held and then corrects you for it. Being brief does not fix it, because the passage looks like real content. The test is one question: can you point at something you actually said or wrote where you hold that position? If not, it goes. Genuine criticism of your code, numbers, or plan is untouched, and a real warning buried in a closing caveat is moved to the top rather than deleted. Skill count 11 -> 12.
- **Upstream review ledger in `FORK.md`.** Every upstream commit now carries an adopt/skip decision and its reason in one table, and `scripts/upstream_baseline.json` advances to `3baf40e`.

## 2026-08-21

### Added

- **`fork` Scheduled upstream check.** `.github/workflows/upstream-check.yml` runs every Monday at 11:00 Asia/Taipei, comparing `agentcrew-academy/harness-starter-kit` `main` against `reviewed_through` in `scripts/upstream_baseline.json`. Unreviewed commits fail the workflow and are listed, with their files, in the run summary. Until now, noticing upstream movement depended on someone remembering to fetch.
- **`fork` `.github/dependabot.yml`.** This kit ships no package manifest, so the only machine-updatable dependency surface is the actions pinned in the workflows; they are checked weekly.

## 2026-08-18

### Added

- **`fork` `install.py --agent cursor` and `--agent codex`.** Cursor gets a flat `~/.cursor/hooks.json` (`version: 1`, event → `[{command}]`), with shell guards on `beforeShellExecution` and the emoji guard on `preToolUse`. Codex merges into an existing `~/.codex/hooks.json`; Windows uses the Python builds and absolute interpreter paths, so `python3 ~/.codex/hooks/...` cannot fail open. `--agent all` now includes both targets.
- **`fork` `docs/cursor-install.md`** (plus `.en.md`): event mapping, and the limit that Cursor `stop` can only follow up, not veto.

### Changed

- **`fork` `verification-protocol` adds bounded live validation.** UI, production, OAuth, deployment, and external-service checks now define a minimal evidence ledger and stop conditions first, use one uniquely named smoke entity, query narrowly, recover stale control once, resume after login, and stop when the required evidence is complete instead of consuming real data or quota on repeated checks.
- **`fork` Codex skill installation now follows the current user-level contract.** `install.py --agent codex` writes to `~/.agents/skills/` instead of creating new legacy `~/.codex/skills/` copies; existing legacy content is preserved. Codex documentation and the verifier now distinguish script live-fire from the `/hooks` trust check.
- **`fork` Codex installation verification now uses real payload live-fire.** The verifier executes all five registered Codex hook types and fails when a registered script is missing instead of checking only `hooks.json`. no-emoji-guard also reads the real `apply_patch` payload's `tool_input.command`, scans only added lines, and preserves transcript / `.srt` path exemptions, closing a registered-but-fail-open path without blocking emoji removal.
- **`fork` POSIX hook installs normalize line endings to LF.** Even when the installer runs in WSL from a Windows CRLF checkout, copied `.sh` hooks no longer fail with `set: invalid option`; `.gitattributes` also pins shell scripts to LF.
- **`fork` The Python hooks now read Cursor payloads.** `beforeShellExecution` puts the command at the top-level `command` field and names the tool `Shell`. A block returns `{"permission":"deny"}`. Claude Code still uses `exit 2` + stderr; Codex still uses `decision` JSON.
- **`fork` claim-guard and lint-gate follow up on Cursor `stop`.** Cursor cannot veto a finished turn, so a hard block would be fake protection. claim-evidence still fails open when there is no `last_assistant_message`, matching the existing contract.
- **`fork` lint-gate also takes the project directory from payload `cwd` / `workspace_roots`.** A user-level Cursor hook's process cwd is `~/.cursor`, so `os.getcwd()` alone is the wrong tree.

---

## 2026-08-15

### Fixed

- **`fork` `--dry-run --agent antigravity/all` is now truly side-effect free.** The installer previously created `~/.gemini/config/skills/` even while claiming that dry-run would write nothing. Directory creation now happens only during a real install, with a cross-platform regression test protecting the contract.
- **`fork` Every hook now reads its payload as bytes, so the Chinese triggers actually fire.**
  All nine hooks used `json.load(sys.stdin)`, which decodes with whatever encoding the locale
  hands the process. On a Traditional Chinese Windows install (cp950), claim-evidence-guard was
  handed "我已經驗證通過，測試全數通過" with an empty ledger and let it through — under the
  default locale and under a strict cp950 stdin alike. **The bilingual half of a kit advertised
  as bilingual had never worked**, and it failed open, so nothing ever looked wrong.
  Found by instrumenting a live Stop hook: a 2.3 KB payload parsed as an empty object, so the
  guard saw no assistant message at all; the same payload read as bytes parsed all eleven fields.
  New suite `hooks/tests/run-encoding-tests.py` sends each hook a payload containing Chinese
  under `PYTHONIOENCODING=cp950`. 6 cases, 0 failures, verified to fail against the old code.
- **`fork` claim-guard fsyncs each ledger line.** A PostToolUse hook is a short-lived process the
  harness can reap before a buffered write reaches disk, producing zero-byte ledgers. Downstream
  that reads as "no evidence", so claim-evidence-guard blocked claims that a real test run
  actually backed. An empty ledger is worse than no ledger.
- **`fork` danger-zone-guard no longer walks past on a quote.** `rm -rf "/"`, `rm -rf "$HOME"`
  and `rm -rf '~'` were all allowed. The guard had inherited test-gate-guard's habit of blanking
  quoted spans — correct there, where quoted text is a sentence mentioning a command; wrong here,
  where it is the path being deleted. Deletions are now matched after removing quote characters
  and only at a command position (start of input, or after `;`, `&&`, `||`, a pipe, optionally
  `sudo`). Force-push and exfiltration checks still use the quote-blanked copy, so a commit
  message describing a force push is not mistaken for one.
- **`fork` Removed danger-zone-guard's Windows shim.** It imported from a sibling folder, but
  hooks install flat, so after installation it imported itself: AttributeError, exit 1 on every
  Bash call, guarding nothing. Replaced by the single cross-platform file.
  **General rule: a flat install means hooks cannot import each other.**

### Changed (upstream)

- **The encoding fix went upstream and was merged**
  ([upstream#2](https://github.com/agentcrew-academy/harness-starter-kit/pull/2)). Upstream then
  added the other half: stdout and stderr need forcing to UTF-8 as well, or a hook blocks
  correctly and then dies with UnicodeEncodeError while printing its own message, leaving the
  user with a traceback instead of a reason. That improvement is pulled back into all nine
  hooks here.

### Added (settings that survive a reinstall)

- **`fork` no-emoji-guard settings now live in `no-emoji-guard.json` beside the script.**
  Prompted by a real incident: the installer copies hook scripts over the top, which turned
  the guard back on for someone who had deliberately switched it off, silently. It now reads
  `{"enabled": false}` — installed and registered but off, one word to switch back, effective
  immediately with no restart — and `{"exempt_path_substrings": [...]}`, both taking
  precedence over the in-script constant. A malformed config falls back to the built-in
  defaults, i.e. it keeps guarding, because a typo must not be a way to switch a guardrail
  off. Five regression cases per build, wired into CI.

### Fixed (installer: duplicate registrations)

- **The same script re-registered with new arguments was added, not replaced.** Adding
  `--codex` changed the command string, and matching was done on the whole string, so the new
  registration landed beside the old one: lint-gate and claim-ledger-tracker each ran twice per
  event on Codex, one of those runs with the behaviour the flag exists to change. Seen on a real
  machine on 2026-08-20.
  Matching is now on the **script path**: an older registration of the same script is removed
  before the new one is written. The cleanup runs unconditionally rather than only when
  something is being added, and a run that only removes still writes the file -- otherwise the
  removal never lands. Other hooks in the same config are untouched. Regression test included,
  running the installer twice to pin idempotency.

### Fixed (cross-agent protocols)

- **Cursor support mistook Claude Code for Cursor, and the two Stop guards stopped blocking.**
  The check was `payload.get("hook_event_name")`, but Claude Code sends that field too
  (capitalised: `Stop`, `PreToolUse`). So claim-evidence-guard and lint-gate -- precisely the
  two whose job is refusing to let a turn end -- answered with Cursor follow-up JSON and
  returned 0, which Claude Code does not act on. The existing suites missed it because their
  synthetic payloads omit the field. Detection is now `cursor_version`, or one of Cursor's own
  event names (lowercase `stop`, `beforeShellExecution`, and so on).
- **Codex on Windows was given the claude-code builds, which speak the wrong protocol.**
  test-gate, danger-zone and no-emoji already have pure-Python codex builds that run fine on
  Windows; they simply were not selected, so a block exited 2 with no JSON for Codex to read.
  Now pointed at the codex builds.
- **lint-gate and claim-ledger-tracker have no jq-free codex build**, so the installer registers
  the Windows build with `--codex` and it answers in Codex's JSON (`{}` to allow,
  `decision: block` to stop). Without the flag, Claude Code behaviour is unchanged.
- Added `hooks/tests/run-agent-protocol-tests.py` (12 cases, in CI): realistic payloads for all
  three agents, asserting each hook answers in the right protocol. Verified to fail (2 cases)
  against the version before this fix.

### Fixed (installer)

- **Windows read-only files no longer break a reinstall**: `robust_rmtree` clears the
  read-only bit before deleting, which `shutil.rmtree` refuses to do on its own.
- **And when removal genuinely fails, it no longer pretends otherwise.** The first version
  swallowed the error with `except Exception: pass` and then copied over the remains with
  `dirs_exist_ok=True`, leaving files that no longer exist upstream while printing "copied"
  and exiting 0. Reproduced with a file held open by another process. It now prints
  `FAILED to replace`, leaves the folder untouched, omits "Installation finished", and exits
  1 — the exit code has to carry it, or a caller chaining on `&&` proceeds regardless. Two
  regression cases in CI (read-only gets fixed and replaced; undeletable is reported, not
  claimed), verified to fail against the previous version.

### Fixed (regression)

- **`fork` Two hooks had reverted to text-mode stdin; restored, with a static check.** The
  change that added Antigravity lifecycle support left `read_payload()` in the file but
  stopped calling it from `main()`, so the helper was orphaned and the hooks quietly went
  back to locale decoding. The encoding suite caught it, two cases red.
  It also showed that grepping for `stdin.buffer` **proves nothing** — only that the string
  is present. `hooks/tests/run-encoding-tests.py` now includes an AST check: any hook that
  actually calls `sys.stdin.read()` / `json.load(sys.stdin)`, or defines `read_payload()`
  without calling it, fails. Parsed rather than grepped, because these files mention both
  calls in their docstrings precisely to explain why not to use them.

### Changed (documentation)

- **`fork` The two new skills and `gemini-md-template/` are now in English**, matching the
  nine existing skills and `claude-md-template/`. Files an agent reads are English
  throughout the repo; `README` and `docs/` stay Chinese-primary with `.en.md` mirrors.
- **`fork` `gemini-md-template/GEMINI.md` rewritten to its own subtraction rule.** The
  original had five sections, including dark mode, glassmorphism, specific typefaces, and
  language version numbers that go stale. Would the model get something wrong without that
  line? No — so it does not belong in a file every project loads. It now has the three
  sections its own README claims (background, hard gates, judgment context), with
  preferences as blanks to fill in.
- **`fork` Antigravity automation advice corrected.** It previously recommended trusting the
  entire home directory and enabling every auto-approve flag at once. Trust is now scoped to
  the projects folder, the trade is stated plainly — turning off prompts makes these hooks
  the only thing left, and they are an interceptor, not a sandbox — and automation is split
  into two stages.

### Added

- **`fork` Cross-platform CI**: Linux / Windows × Python 3.11 / 3.14 run core Python compilation, danger-zone/test-gate/encoding regressions, the installer dry-run contract test, and a full dry-run plan.
- **`fork` danger-zone-guard** (fifth interceptor hook): blocks recursive deletion of root or
  home, deletion of `.git`, force pushes to protected branches, and credential exfiltration.
  25 regression cases across both builds.
- **`fork` Google Antigravity (AGY) support**: `docs/antigravity-install.md` (+ `.en.md`),
  the `gemini-md-template/` starter rules, and multi-agent targets in `install.py`.
- **`fork` Two workflow skills**: `verification-protocol` (verify as you change, no fake fixes)
  and `task-orchestrator` (Research → Plan → Build → Verify, with context management).
- **`fork` `scripts/install.py`**: one command reproduces the whole setup. Detects the platform,
  **merges** into the existing settings file rather than overwriting, backs it up first, writes
  atomically, re-reads to confirm valid JSON, is idempotent, and leaves existing skill folders
  alone.
- **`fork` `scripts/verify-install.py`**: test-fires each installed hook with a synthetic payload
  and checks the answer, instead of reading the config and calling it fine.
- **`fork` test-gate-guard** (fourth interceptor hook): blocks a single command where a test and
  a `git commit`/`git push` are joined with `;` instead of `&&`. Came out of a real incident, and
  ships with the regression suite from its own first-day false positive.
- **`fork` Windows hook builds** (`hooks/*/windows/`): Python versions of claim-guard and
  lint-gate. The shell builds need `jq`, which a stock Windows box does not have — and without it
  they `exit 0`, which means "allow".
- **`fork` Per-project lint-gate config `.lint-gate.json`**: register globally once; a project
  without the file is untouched, and any project opts in by dropping one in, effective
  immediately with no restart.
- **`fork` `docs/windows-install.md`** (+ `.en.md`): the three silent Windows failure modes and
  the fix for each, all verified on a real machine.

### Changed

- **`fork` README is now product- and support-matrix-first**: Claude Code, Codex, Antigravity / Gemini, and Cursor hook / skill / installer capabilities are stated separately; `--agent all` is no longer described as automatically registering Codex or Cursor.
- **`fork` `AGENTS.md` is reduced to installation safety invariants plus repository maintenance rules**: the nontechnical-user installation contract remains, while repo work now follows branch → PR → CI → merge and documentation-only cleanup does not mechanically require a changelog or release.
- **`fork` `AGENTS.md` rewritten as the single source of truth** for any AI agent;
  `CLAUDE.md` reduced to a thin Claude Code specific patch.
- **`fork` Documentation language flipped**: Traditional Chinese is primary, English mirrors
  live in `*.en.md`.
- **`fork` `.gitignore` covers `__pycache__`**: six `.pyc` files were tracked upstream.

---

## 2026-08-14 (upstream)

- Added `claude-md-template/`: a starter `CLAUDE.md` written to the fifth-generation model
  guidance, plus three optional rules files.

## 2026-08-12 (upstream)

- Added the info-diet skill: works out where your attention actually goes, computed locally.

## 2026-08-09 (upstream)

- All three interceptor hooks gained a Codex build with identical judging logic.
- Added the review-loop skill: stops sections disappearing silently across document revisions.
