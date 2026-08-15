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

## Rules Integration (GEMINI.md)

Antigravity supports hierarchical rule resolution (Global: `~/.gemini/GEMINI.md`, Project: `GEMINI.md` or `.agents/rules/*.md` in repo root).

1. Review `gemini-md-template/GEMINI.md` in this repository.
2. Merge its guidelines into your `~/.gemini/GEMINI.md` or your project root.
3. Modular rules from `gemini-md-template/rules/` can be copied into `.agents/rules/` or `~/.gemini/config/rules/`.

---

## Trusted Workspaces & Auto-Approve Configuration

To avoid repeated permission prompts during automated test runs and file edits, configure `~/.gemini/antigravity-cli/settings.json`:

### 1. Set Trusted Workspaces to User Home
Setting your root user directory covers all current and future projects automatically:

```json
"trustedWorkspaces": [
  "C:\\Users\\<your-username>"
]
```

### 2. Enable Full-Auto Mode

```json
"agent_features": {
  "auto_run_tests": true,
  "smart_context_retrieval": true,
  "web_search_enabled": true,
  "browser_testing_enabled": true,
  "mcp_enabled": true,
  "auto_approve_commands": true,
  "auto_approve_file_edits": true,
  "skip_permission_prompts": true,
  "auto_execution_mode": "full_auto"
}
```

---

## Verify Installation

Run self-verification:

```bash
python scripts/verify-install.py --agent antigravity
```
