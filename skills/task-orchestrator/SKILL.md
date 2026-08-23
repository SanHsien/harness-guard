---
name: task-orchestrator
description: "Decompose complex multi-file or large-scale tasks into clean lifecycle stages: Research, Plan, Build, and Verify. Use for large refactoring, new feature implementation, or subagent workflow orchestration."
allowed-tools: Agent Read
---

# Task Orchestrator — Four Stages, In Order

Big changes go wrong in a particular way: you start editing while you are still working
out what is there, the context fills with search output, and by the end nobody can say
which decision was made deliberately and which one just happened.

Four stages, and the discipline is not skipping ahead.

## 1. Research — read only

Find the files that matter, the dependencies, the edge cases, the existing conventions.
**No edits in this stage**, including obvious ones. An edit made before you have the whole
picture is a decision made on partial information, and it is the hardest kind to notice
later.

Finish by being able to name the files you will touch and why.

## 2. Plan — decide before building

Write the implementation steps in order, name the decisions that have more than one
defensible answer, and list what each step affects. This is where you find out that step
four contradicts step two, which is much cheaper here than in the editor.

If the user is waiting on a plan, show it before building. A plan reviewed in thirty
seconds saves an afternoon.

## 3. Build — one step at a time

Work the plan in order. Keep each step small enough to describe in one sentence, and stay
inside the project's existing conventions rather than importing your own.

When something in the plan turns out to be wrong — and on a large task, something will —
say so and adjust the plan explicitly. Silently building something other than what was
agreed is how the final result stops matching the review.

## 4. Verify — exit code, not opinion

Run the tests, the type check, and whatever else the project uses. Exit code 0 is the
result; a reading of the diff is not. See the `verification-protocol` skill for what
counts as evidence and what counts as a fake fix.

## Keeping the context clean

Research is what fills a context window: greps that return two hundred lines, files read
in full for the sake of three functions. Two habits:

**Send the search out.** When a search will produce a lot of output, hand it to a subagent
and ask for the conclusion — file paths, line numbers, and the answer — not the raw
output. The main thread should receive the finding, not the transcript.

**Write down conclusions, not logs.** Record what you learned in a couple of lines. Pasting
whole outputs into the main thread buys nothing that a summary and a path do not.

Worked examples for two common shapes of task are in
[`references/decomposition-playbook.md`](references/decomposition-playbook.md).
