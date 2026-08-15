> English | [中文版](README.md)

# Five Guardrail Hooks, Eleven Workflow Skills, and Starter Rule Templates

> **This is a fork.** It adds Windows-native Python builds, cross-agent support (Claude Code, OpenAI Codex, Google Antigravity, Cursor), and a self-verification script (`verify-install.py`) that test-fires hooks instead of guessing. Windows users start from [`docs/windows-install.en.md`](docs/windows-install.en.md); Antigravity users start from [`docs/antigravity-install.en.md`](docs/antigravity-install.en.md).
>
> What changed in each release: [`CHANGELOG.en.md`](CHANGELOG.en.md). How this fork differs from upstream and how to sync: [`FORK.md`](FORK.md).

Have you ever experienced this: you instruct your AI assistant to "always run tests after editing code", it complies three times, and on the fourth turn forgets without saying a word; or it runs a catastrophic deletion command or leaks sensitive tokens.

That is why this kit exists.

Rules are just text. When conversations get long, text gets diluted. The approach here is: **Don't beg it; block it.** Turn desired behaviors into automated programmatic guardrails.

---

## One-Command Reproducibility

```bash
# For Claude Code
python scripts/install.py --dry-run --hooks all --skills all

# For Google Antigravity (AGY)
python scripts/install.py --agent antigravity --skills all

# For all supported agents
python scripts/install.py --agent all --hooks all --skills all
```

Restart your agent, then verify:

```bash
python scripts/verify-install.py
```

Exit code 0 confirms all installed guardrails actually fire and respond correctly.

---

## Five Guardrail Hooks

1. **claim-guard**: Tracks tool calls quietly and reconciles completion claims against actual test/search logs before allowing the turn to end.
2. **no-emoji-guard**: Strictly filters emojis from documents, comments, and commit messages based on official Unicode definitions.
3. **lint-gate**: Runs checks before wrap-up. Windows build supports per-project `.lint-gate.json` opt-in.
4. **test-gate-guard**: Blocks commands chaining tests and git commits with `;` instead of `&&` (preventing broken code shipping).
5. **danger-zone-guard (New in fork)**: Intercepts catastrophic deletions (`rm -rf /`, `rm -rf ~`, `rd /s /q C:\`), accidental `.git` removal, force pushes to primary branches, and `.env`/secret exfiltration.

---

## Eleven Workflow Skills

1. **explain**: Rewrites complex explanations in plain language without jargon.
2. **polite**: Shifts tone between warm empathy and business professional.
3. **first-principles**: Re-examines problems from first principles.
4. **checkpoint**: Structured session closure and commit synchronization.
5. **neat-freak**: Mechanical fact reconciliation engine.
6. **review-loop**: Prevents silent content loss during document revisions with paragraph locking and web review UI.
7. **info-diet**: Computes local attention and browsing structure with complete privacy.
8. **asd-ste100**: Simplified Technical English rewriting for unambiguous tool instructions.
9. **iso-24495**: Plain language writing following ISO 24495-1 standards.
10. **verification-protocol (New in fork)**: Modify-then-verify and zero-dummy standards.
11. **task-orchestrator (New in fork)**: Four-stage lifecycle task decomposition (Research → Plan → Build → Verify) and context management.

---

## Starter Rule Templates

- **`claude-md-template/`**: Minimal `CLAUDE.md` template based on latest model guidelines.
- **`gemini-md-template/` (New in fork)**: Hierarchical `GEMINI.md` rules for Google Antigravity and Gemini CLI.

---

## Before installing, have the AI read the scripts to you

These tools intercept what the AI is allowed to do, and that affects everything you work on
afterwards. Have it read each script out loud, or at minimum explain what each one does. That
holds for this folder and for any bundle of scripts you find online — convenience is not a
reason to install something.

---

## License

MIT — see [`LICENSE`](LICENSE).

This kit is a fork of [agentcrew-academy/harness-starter-kit](https://github.com/agentcrew-academy/harness-starter-kit),
and several hooks are in turn adapted from earlier work. The original authors and sources are
listed in [`NOTICE`](NOTICE). Keep that file attached if you redistribute or reuse this — it is
the one thing MIT actually requires of you.
