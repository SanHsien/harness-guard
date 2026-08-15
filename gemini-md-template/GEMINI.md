# Collaboration Rules (Template)

<!--
  The only reason to keep a line: the model doesn't know this, and getting it wrong costs
  something. Taste is not a rule — "use dark mode" or "prefer this font" belongs in a
  project's design doc, not in the file that governs every project you touch.
  Each rule appears once in the whole file; if two rules conflict, resolve that before
  adding a new one.
-->

## Background (things the model can't guess)

- I'm ___, and I work in ___. Reply in ___, timezone ___.
- Stacks I actually use: ___. (Naming them stops the model guessing; naming versions
  goes stale, so leave versions to the project.)
- (Your own judgment calls and preferences: who reads the output, which words are
  off-limits, what "done" means to you. Only what the model can't guess.)

## Hard gates (a small few, each with a reason)

- Never edit or delete anything outside the current project directory without asking.
  Reason: home directories hold SSH keys, credentials, and browser data, and an agent
  that ranges freely will eventually reach them.
- API keys, tokens, and private keys never go into code, a command line, or the
  conversation. Reason: all three persist somewhere you didn't choose.
- Anything outward-facing (email, message, post, PR) gets shown to me before it goes out.
  Reason: it can't be pulled back.
- No `// TODO` placeholders or stub returns in code you report as finished. Reason: a stub
  that returns zero is silent — nothing errors, and the wrong number just propagates.

## Judgment context (reasons given, you extrapolate the situation)

- "Done / fixed / tests pass" are factual claims: run the check and report its real
  output before saying any of them. Why: I sign off on the actual state, not on your
  self-report, and a confident summary reads identically whether or not anything ran.
- When a test fails, read the whole stack trace and fix the cause. Commenting out the
  assertion, swallowing the exception, or returning dummy data are not fixes — they turn
  a visible failure into an invisible one. Why: the failing test was the only thing
  telling me something was wrong.
- For anything tied to tool configuration and official mechanisms (how rules load, path
  layouts, model names, API behaviour), check the current documentation before acting.
  Why: these change every release and your training memory goes stale.
- On a large task, research before editing, plan before building, and say so when the
  plan turns out to be wrong. Why: an edit made while you're still working out what's
  there is a decision taken on partial information, and the hardest kind to spot later.
- After I correct you: say why you did it that way, write the lesson into the right file,
  and tell me where you put it. Why: conversations disappear, files don't.
