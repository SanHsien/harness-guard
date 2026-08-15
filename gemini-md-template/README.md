# A Starter Rules File for Antigravity and Gemini CLI

The same idea as [`claude-md-template/`](../claude-md-template/README.md), in the format
Google Antigravity and Gemini CLI read: a "how we work together" file the agent loads on
its own, so you stop re-explaining your preferences every conversation.

## What's inside

- `GEMINI.md` — the main template, in three parts: **Background** (things only you know),
  **Hard gates** (a handful of things that must never go wrong, each with its reason), and
  **Judgment context** (the reasoning spelled out, so the model can extrapolate to
  situations you didn't list).
- `rules/` — three optional add-ons: verification discipline, subagent workflow, and
  defensive coding. Install whichever you want; skipping any of them changes nothing else.

## Where the files go

Antigravity loads rules in layers, most specific last:

```
~/.gemini/GEMINI.md              global, applies everywhere
<project>/GEMINI.md              this project only
<project>/.agents/rules/*.md     topic files for this project
```

`rules/*.md` go in `~/.gemini/config/rules/` for global effect, or `.agents/rules/` inside
a project.

## Installing

The skills ship separately from the rules file:

```bash
python scripts/install.py --agent antigravity --skills all
```

That copies this repo's skills into `~/.gemini/config/skills/`, where Antigravity picks
them up on demand.

The rules file is merged by hand, on purpose:

1. Open your global rules file — `~/.gemini/GEMINI.md`, or
   `C:\Users\<you>\.gemini\GEMINI.md` on Windows.
2. **If it already has content, merge — do not overwrite.** Go through this template a
   section at a time and keep only what applies to you. A rule that already exists in your
   file should not be added twice; two copies dilute each other.
3. Fill in the blanks (`___`). Leaving them blank means it isn't really installed.

## Keeping it short

This template is maintained by subtraction. Every time you want to add a line, ask: **would
the model get something wrong without it?** If not, don't add it.

The line that fails this test most often is taste. "Use dark mode", "prefer this font",
"always use this framework" — those belong to a project, not to every project you will ever
open. Put them in that project's `GEMINI.md`, and keep the global file for things that are
true regardless of what you are working on.
