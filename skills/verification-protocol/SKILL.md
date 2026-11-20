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

## 5. Delegated work: the gate's verdict is the evidence

When work is handed to another agent through agent-relay (`C:\GitHub\agent-relay`),
its acceptance gate (`agent_relay/gates.py`, SPEC section 11) is what proves the work,
not the worker's summary. The sender asks for a failing test first with `--tdd`; the
receiving side sets the gate itself in `dispatch.verify` (the verify command, plus
`governance` for agent-governance-toolkit path, credential and subprocess policy).
Then read the verdict:

- Only `ok` counts as done. `skipped` means the receiver had no gate configured: relay
  treats it as passing, but it is no evidence, so it is "not done" here.
  `verification-failed`, `unverified`, `guarded`, `stub-rejected`, `tdd-not-proven` and
  `policy-violation` are all "not done".
- If governance was asked for but the toolkit did not load, the gate returns
  `unverified` on purpose. Install it (`AGENT_GOVERNANCE_PATH` or
  `C:/GitHub/agent-governance-toolkit`) rather than switching to
  `governance_fallback: "builtin"`; a degraded run must be reported as degraded.
- A check marked "not run" is not a pass, whatever else the report says.

## 6. 使用者看得到的結果：綠燈之外還要親眼看過

改到畫面、指令輸出、報告裡的數字或事實這類會被人直接看到的結果時，第 1 至 5 節照做，
另外加上這五條。反例、正例與檢查項範本在
[`references/observable-checks.md`](references/observable-checks.md)。

1. 動工前先列檢查項，每項寫明要哪一類證據（截圖、錄影、指令原始輸出、實際資料）；缺一類就不算過。
2. 測試、lint、建置綠燈是必要條件，不能代替打開實際產出看過。
3. 不可能失敗的執行不算證明：先在同樣前提下看到它失敗，再看到它通過。
4. 截圖要實際打開看內容，檔案存在或有圖說都不算；截圖前後跑
   `python C:\GitHub\agent-safety-checks\tools\screen_privacy.py`。
5. 量一個改過的值，證明正在跑的是工作目錄裡的程式，不是舊行程、快取或舊的安裝副本。

推算、湊數或只看過一個樣本得到的結論，照實寫「推算」「只驗一個樣本」或「未驗證」，不寫成事實。

## The loop

1. Finish the change.
2. Work out this project's stack and its test command (see
   [`references/test-matrix.md`](references/test-matrix.md)).
3. Run it.
4. Exit code 0? Record what you ran and what it printed — that is the evidence you report.
5. Non-zero? Read the full trace, find the root cause, fix that, and go back to step 3.

Report the command and its real output. "Tests pass" without the command that produced
that result is the claim this whole protocol exists to make unnecessary.

## Do not repeat valid checks by habit

After a relevant check passes, retain its actual command, exit code, output path,
timestamp, and complete input state (HEAD plus changed/untracked input hashes).
The primary may reuse worker evidence only after checking that inputs, dependencies,
configuration, environment, and acceptance requirements match, and the repository
does not require an independent rerun. HEAD alone does not bind uncommitted edits.
Changed inputs, stale external state, missing logs, or failures require the narrowest
relevant rerun. Independent checkers and mandatory delivery gates still run.
Once requirements are satisfied, stop. Do not add model review or repeat live checks
without a new change, failure, or unresolved concern.
