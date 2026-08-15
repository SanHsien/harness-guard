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

## Verify Installation

Run self-verification:

```bash
python scripts/verify-install.py --agent antigravity
```
