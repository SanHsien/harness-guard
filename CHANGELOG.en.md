> English | [中文版](CHANGELOG.md)

# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), newest first.
Entries marked `fork` are this fork's changes relative to
[upstream](https://github.com/agentcrew-academy/harness-starter-kit).

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
