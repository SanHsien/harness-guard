---
name: explore-unknowns
description: Maps a task's unknowns via a guided quadrant walk (known knowns, known unknowns, unknown knowns, unknown unknowns) into a four-quadrant map. Use when a request is ambiguous or the domain unfamiliar.
---

# Explore Unknowns

> The quadrant-walk methodology in this skill follows the approach Thariq
> Shihipar describes in "A Field Guide to Fable: Finding Your Unknowns"
> (https://x.com/trq212). The wording here is our own; the credit for the
> method is his.

What you hand the model is never the whole job. A prompt describes the work;
the work itself lives in a codebase, a domain, and a head full of intent
nobody has written down. Everything in that gap is an unknown.

Unknowns get more expensive the later you find them. One surfaced before any
code is written costs a conversation. The same one surfaced three pull
requests in costs the three pull requests.

This skill is a guided conversation: the **quadrant walk**. Together with the
user you fill in a four-quadrant map of the task, one quadrant per stage, and
the user walks away holding the completed map. The map is the deliverable;
implementation is a different task that starts only after the map is handed
over.

Two moves apply at every stage:

- **Reacting beats imagining.** Never ask the user to describe what they want
  when you can hand them something concrete to react to — a rendered option,
  a clickable mock, a decisions table. Reacting extracts knowledge the user
  has but cannot articulate unprompted.
- **Every artifact assembles the reply.** End each artifact with the user's
  next message pre-drafted: steal/skip chips, resonate checkboxes, a
  decisions table, a copyable sharpened prompt — so their reaction becomes
  their next message with near-zero typing.

## The Quadrant Walk

Five stages, walked in order, one at a time. **When you enter a stage, read
its reference file and follow it.** Name the current quadrant as you go — the
user should always know where they stand on the map — and finish the stage in
front of you before opening the next.

1. **[Known knowns](references/stage-1-known-knowns.md)** — scan the
   territory, then open with the settled ground.
2. **[Known unknowns](references/stage-2-known-unknowns.md)** — the questions
   you can name; resolve them one at a time.
3. **[Unknown knowns](references/stage-3-unknown-knowns.md)** — extract the
   taste and tacit context nobody has put into words.
4. **[Unknown unknowns](references/stage-4-unknown-unknowns.md)** — sweep the
   territory for landmines.
5. **[Hand over the map](references/stage-5-hand-over-the-map.md)** — the
   completed four-quadrant map, the walk's only done-condition.

When the user moves on to build, review, or merge what the walk mapped, read
[after the walk](references/after-the-walk.md) — the map lives on past
planning.

## Rules

- Walk the quadrants in order, one stage at a time, naming the current
  quadrant. The walk ends with the map in the user's hands — no map, not
  done.
- Stages order the walk; they never embargo information. A finding that
  materially bears on a decision in flight is disclosed the moment you have
  it, then filed on the map under its quadrant — never held back for its
  stage's scheduled turn.
- Nothing closes off-screen. Any question or judgment call the map records as
  closed must have been shown to the user first — including ones the
  territory answered.
- Claims about the territory cite real files actually read; invented data is
  labeled as such. A fabricated specific destroys the map's authority.
- HTML artifacts are self-contained single files: inline CSS/JS, no external
  requests, plausible fake data over lorem ipsum.
- Stop at every stage boundary that needs the user's reaction. Never barrel
  into implementation on unconfirmed guesses — implementing is a separate
  task that begins after the map is delivered.
