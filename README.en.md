English | [中文版](README.md)

# Harness Guard

[![CI](https://github.com/SanHsien/harness-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/SanHsien/harness-guard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Turn “please remember the rules” into executable checks that can actually block an action.**

Harness Guard is a guardrail kit for AI coding agents: five hooks, twelve optional workflow skills, Claude / Gemini rule-file templates, a reproducible installer, and a live-fire installation verifier. Windows support is a major focus of this fork.

This repository is a fork of [`agentcrew-academy/harness-starter-kit`](https://github.com/agentcrew-academy/harness-starter-kit). See [`FORK.md`](FORK.md) and [`NOTICE`](NOTICE) for upstream provenance, fork-specific changes, and attribution.

## Why it exists

Text instructions can fade in long sessions. Hooks are different: they execute programmatic checks before or after agent actions, or when a turn is about to end.

Harness Guard focuses on failure modes with practical consequences:

- claiming tests passed without evidence that a test actually ran;
- letting a failed test continue into `git commit` / `git push` because shell commands were chained incorrectly;
- destructive deletion, force-pushing a protected branch, or exfiltrating `.env` / private-key files;
- wrapping up without passing a project-defined lint or check command;
- explicitly disallowing emoji in workflows where that is a project requirement.

These guardrails are defense-in-depth, not a sandbox or formal policy engine. They use pattern matching and agent hook interfaces, so false positives and false negatives remain possible.

## Five guardrail hooks

| Hook | What it does |
|---|---|
| `claim-guard` | records tool evidence and reconciles completion claims before the turn ends |
| `test-gate-guard` | blocks unsafe test + `git commit` / `git push` command chaining |
| `danger-zone-guard` | blocks selected catastrophic deletions, force-pushes to protected branches, and sensitive-file exfiltration |
| `lint-gate` | runs project checks before wrap-up; Windows can opt in per project with `.lint-gate.json` |
| `no-emoji-guard` | blocks emoji in selected write flows; optional and preference-oriented |

See [`hooks/`](hooks) for platform-specific implementations and interface details.

## Twelve workflow skills

`explain`, `polite`, `first-principles`, `checkpoint`, `neat-freak`, `review-loop`, `info-diet`, `asd-ste100`, `iso-24495`, `phantom-pushback`, `verification-protocol`, and `task-orchestrator`.

They are optional workflows, not required dependencies of the five guardrail hooks. See [`skills/`](skills).

## Support matrix

| Agent / environment | Hooks | Skills / rules | Installation status |
|---|---|---|---|
| **Claude Code** | all five hooks; Windows selects Python builds where needed | `~/.claude/skills/` + CLAUDE rule templates | automated by `install.py` |
| **OpenAI Codex** | all five hooks; Windows uses Python builds and absolute interpreter paths | `~/.agents/skills/` | `install.py --agent codex` |
| **Google Antigravity / Gemini** | no equivalent hook registration in this repo today | skills + `GEMINI.md` templates | `install.py --agent antigravity` installs skills |
| **Cursor** | all five hooks, written to `~/.cursor/hooks.json` in Cursor's flat format | `~/.cursor/skills/`; also merged into `~/.agents/skills/` when that directory already exists | `install.py --agent cursor` |

Accordingly, `--agent all` currently means **Claude Code + Antigravity + Cursor + Codex**. Cursor's `stop` event cannot veto a finished turn, so claim-guard and lint-gate follow up there instead of blocking.

## Quick start

### Claude Code

Preview without changing configuration:

```bash
python scripts/install.py --dry-run --hooks all --skills all
```

Then install:

```bash
python scripts/install.py --hooks all --skills all
```

### Google Antigravity / Gemini skills

```bash
python scripts/install.py --dry-run --agent antigravity --skills all
python scripts/install.py --agent antigravity --skills all
```

### Cursor

```bash
python scripts/install.py --dry-run --agent cursor --hooks all --skills all
python scripts/install.py --agent cursor --hooks all --skills all
```

User-level Cursor hooks go in `~/.cursor/hooks.json`. Shell guards use `beforeShellExecution`; the emoji guard uses `preToolUse` (`Write`). See [`docs/cursor-install.en.md`](docs/cursor-install.en.md).

### OpenAI Codex

```bash
python scripts/install.py --dry-run --agent codex --hooks all --skills all
python scripts/install.py --agent codex --hooks all --skills all
```

The installer **merges** into an existing `~/.codex/hooks.json` and uses absolute `python` / `python3` paths, so Windows does not silently fail on `python3 ~/.codex/hooks/...`. Skills go to Codex's current user-level location, `~/.agents/skills/`; existing legacy copies under `~/.codex/skills/` are not deleted or moved automatically.

Hooks are enabled by default. If you previously disabled them, set `[features].hooks = true` in `config.toml`. After adding or changing a registration, run `/hooks` in Codex to inspect and trust the current definition. `verify-install.py` live-fires the scripts directly, but it cannot replace the TUI trust check.

### All automated targets

```bash
python scripts/install.py --dry-run --agent all --hooks all --skills all
python scripts/install.py --agent all --hooks all --skills all
```

The installer is designed to **merge rather than replace** existing configuration. Claude Code settings are backed up before a real write, and existing same-name skill folders are left untouched unless `--force` is explicitly requested.

Hook scripts themselves are copied over the top, so a setting edited inside a script is lost on the next install — silently, and in the direction of "blocking again". Settings that must survive a reinstall go in a JSON file beside the script, which the installer never writes:

```jsonc
// ~/.claude/hooks/no-emoji-guard.json
{ "enabled": false }                          // installed and registered, but off
{ "exempt_path_substrings": ["/my-notes/"] }  // exempt one subtree
```

`.lint-gate.json` works the same way, per project. A malformed config falls back to the built-in defaults — that is, it keeps guarding — because a typo must not be a way to quietly switch a guardrail off.

## Verify the installation

After installing Claude Code hooks, restart the agent and run:

```bash
python scripts/verify-install.py
```

The verifier does more than inspect configuration: it feeds synthetic payloads into installed hooks and checks their actual allow / block behavior. Exit code `0` means the items it checked passed.

It primarily verifies Claude Code hooks and the Antigravity skills directory, and live-fires Cursor / Codex hooks when those installs are present.

## Windows

Do not rely on the `jq`-dependent shell builds in a native Windows environment. The Claude Code installer selects Python builds where required so missing `jq` or a WSL `bash` path does not silently turn a guardrail into fail-open behavior.

See [`docs/windows-install.en.md`](docs/windows-install.en.md). Antigravity / Gemini users should see [`docs/antigravity-install.en.md`](docs/antigravity-install.en.md).

## Before installing

These scripts modify agent configuration, and hooks can intercept future actions. Before installing any guardrail bundle from the internet, read the scripts or ask your agent to explain:

1. which files will be copied;
2. which settings will be modified;
3. which events can block an action;
4. how to disable and remove it.

You do not need every hook. Installing only the guardrails that match your actual risks is usually better than accumulating more rules.

## If you are not comfortable with the terminal

Give the repository URL to an AI coding agent and ask it to read [`AGENTS.md`](AGENTS.md), explain the changes in plain language, run the installer in dry-run mode first, and install items one at a time. Do not ask it to skip preview and verification.

## Development and verification

CI runs the core Python syntax / regression checks, installer dry-run contract test, and existing hook test suites on Linux and Windows.

Main regression commands:

```bash
python hooks/danger-zone-guard/tests/run-tests.py
python hooks/test-gate-guard/tests/run-tests.py
python hooks/tests/run-encoding-tests.py
python -m unittest discover -s tests -p "test_*.py"
```

Repository maintenance and installation rules live in [`AGENTS.md`](AGENTS.md). Release history lives in [`CHANGELOG.en.md`](CHANGELOG.en.md).

## License

MIT License — see [`LICENSE`](LICENSE). Original authors, fork provenance, and adapted work are listed in [`NOTICE`](NOTICE).
