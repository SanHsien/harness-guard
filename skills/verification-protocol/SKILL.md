---
name: verification-protocol
description: "Enforce modify-then-verify, zero-dummy, and bounded live-validation standards. Use when modifying code, running tests, diagnosing failures, validating builds, or verifying UI, production, OAuth, deployment, and external-service behavior before completion."
allowed-tools: Bash Agent Read
---

# Verification Protocol — Change It, Then Prove It

Reading a diff and concluding it looks right is not verification. It costs nothing to
say "fixed" and it feels the same from the inside whether or not anything was run. This
skill is the working practice that keeps that from happening; claim-guard is the hook
that catches you when the practice slips.

Three rules, each with the reason it exists.

## 1. Change it, then run it

Anything added, modified, or refactored gets its test, build, or lint command actually
run in the terminal before you report back. The exit code is the evidence. Your reading
of the code is not.

This matters because the failure is silent: code that looks correct and was never
executed produces exactly the same confident summary as code that passed.

If a change genuinely cannot be verified automatically — a UI behaviour, a hardware
path, a third-party account you do not have — say "not verified, needs manual
confirmation" and name what needs confirming. That sentence is always available, and it
is never the wrong answer.

## 2. No fake fixes

When a test fails, none of the following count as fixing it:

- commenting out the failing case or the assertion
- swallowing the exception (`except Exception: pass`)
- returning hardcoded or dummy data so the caller stops complaining

Each of these converts a visible failure into an invisible one, which is strictly worse
than the failing test you started with. See
[`references/zero-dummy-guide.md`](references/zero-dummy-guide.md) for the common shapes
and what to do instead.

## 3. Read the log before touching the code

Read the whole stack trace and the failing line first, then find the root cause, then
make one precise change. Changing things to see what happens turns one known failure into
several unknown ones, and it hides the original cause under the edits.

## 4. Bound live and external verification

UI, production, OAuth, deployment, and third-party checks can consume real accounts,
tokens, data, or usage quota. Before starting one, read
[`references/bounded-live-validation.md`](references/bounded-live-validation.md), define
the minimum evidence and stop conditions, then stop as soon as they are met. A second
smoke entity or repeated query is not extra confidence unless it proves a distinct
requirement.

## The loop

1. Finish the change.
2. Work out this project's stack and its test command (see
   [`references/test-matrix.md`](references/test-matrix.md)).
3. Run it.
4. Exit code 0? Record what you ran and what it printed — that is the evidence you report.
5. Non-zero? Read the full trace, find the root cause, fix that, and go back to step 3.

Report the command and its real output. "Tests pass" without the command that produced
that result is the claim this whole protocol exists to make unnecessary.
