---
name: polite
description: "Two-mode tone rewriting: A Warm & Empathetic (customer service replies, delivering bad news, apologies, reassurance, declining a request; too cold, too blunt, soften it up); B Formal Business (outward-facing emails, proposals, announcements, follow-up/reminder emails; too casual, too abrasive, more formal, business tone, more official)."
allowed-tools:
  - Read
  - Edit
metadata:
  source: Adapted and translated from hardikpthv/agent-skills (MIT)'s empathetic-tone-basic and professional-tone-basic, merged into a single skill. See NOTICE at the repo root.
---

# Polite: Tone Rewriting (Warm & Empathetic / Formal Business)

Determine the mode before rewriting. Shared rule for both modes: **never invent circumstances or excuses for the other person** (e.g., assuming they "must have been busy lately" as the reason they didn't reply) — don't bring up situations they never actually mentioned; deal only with the facts or the request itself. Otherwise it tends to read as guilt-tripping (confirmed case, 2026-07-04: a follow-up email's line "I know things have probably been busy on your end" was flagged as landing that way).

## Determining the mode

| Signal | Mode |
|---|---|
| "too cold," "too blunt," "soften it up," "more empathy," "make it more reassuring," "this reads as harsh"; customer service replies, bad news, apologies, declining a request, reassurance | **A Warm & Empathetic** |
| "too casual," "this comes off too harsh," "more formal," "business tone," "more official"; outward-facing emails, proposals, follow-up/reminder emails, announcements | **B Formal Business** |

**Neither mode applies to**: spinning the truth so the other person draws the wrong conclusion, manipulative reassurance, legal documents, safety warnings, factual incident reports, or casual chatter in an internal group chat.

## Mode A: Warm & Empathetic

Core principles:

1. **Acknowledge first, then address**: put the feeling or situation ahead of the solution. "That's genuinely frustrating — let's figure this out" beats jumping straight to the fix. Note: only acknowledge circumstances or feelings the other person has actually stated (see the shared rule above).
2. **People before policy**: "I want to help you with this" comes before "per policy."
3. **Validate without judging**: "That makes complete sense" / "It's totally fair to ask that."
4. **Soften commands**: turn "You need to..." into "Whenever it's convenient, you could..."
5. **Use warm, plain words**, lean on "you/we," and keep the reassurance short — a brief warm line beats an elaborate one.
6. **Share the responsibility**: "we dropped the ball on this" beats "an error occurred."
7. **Close with support**: give a next step and leave the door open. "Let me know if anything's unclear."

Technique: the go-to shape is **acknowledge → reassure → help → invite**; turn blame ("you forgot to...") into a neutral statement ("it looks like this step got missed"); turn "no" into a path forward ("I can't do that, but here's something that might work"); keep sentences unhurried and steady, and don't stack up exclamation points.

Before / After:

**Before**: Your application has been denied. You did not follow the required steps.
**After**: Thanks for sending this in — it looks like a couple of steps got missed, so I can't approve it just yet. That said, I can walk you through exactly what's needed, and we'll get it sorted together.

**Before**: This item is out of stock. Please check back later.
**After**: Sorry about this — it's actually out of stock right now, and I know that's disappointing. I can let you know the moment it's back in, or point you toward a similar option in the meantime, whichever works better for you.

Don't overdo it: warmth isn't a pep talk. Avoid empty positivity ("everything happens for a reason!"), fake familiarity, or burying the real answer under soft language. Be considerate, but still say the actual answer clearly.

## Mode B: Formal Business

Core principles:

1. **Formal tone**: cut casual slang; a normal business email can keep natural connecting phrases — it doesn't need to sound stiff in every sentence.
2. **Precise and concise**: replace vague or padded phrasing with specific, direct statements.
3. **Polite and measured**: courteous, neutral, no sarcasm, confident without being pushy (see the shared rule above).
4. **Structured**: state the purpose up front, with clear paragraphs, one point per paragraph.
5. **Clear close**: include a concrete next step and sign off appropriately.
6. **Consistent formatting**: correct forms of address, no all-caps or exclamation-heavy passages, no emotionally charged language.
7. **Lead with yes on conditional requests**: when someone makes a request with a condition or prerequisite attached, give the positive answer first (yes, that works), then frame the prerequisite as something that speeds things up or improves accuracy — not as a gate that blocks them ("can't do it unless..."). This comes up often in business-development or client inquiries: confirm it's doable first, and present the prerequisite as the next action item, not a reason to say no.

Technique: turn a casual opener ("Hey, so...") into a purposeful one ("Following up on..."); replace filler ("kind of," "roughly," "ASAP") with precise wording ("approximately," "by end of day Friday"); rewrite complaints or emotional statements as a neutral fact plus a request; turn "I need X before I can do this" into "If you can get me X first, I can get started right away / be more accurate" — the prerequisite shifts from a limitation into something the other person can proactively do; close with a clear next step and an appropriate sign-off.

Before / After:

**Before**: Hey, so this thing is kind of running late and it's honestly a pain. Can you speed it up??
**After**: Following up to flag that this deliverable is currently behind schedule, which may affect the downstream timeline. Could you provide an updated completion estimate by end of day, please?

**Before**: We crushed it this quarter, numbers are great.
**After**: The team delivered strong results this quarter, with several key metrics exceeding original targets.

**Before**: I can teach this, but you'll need to set me up with an account first or I can't test anything.
**After**: Happy to teach this. One thing that would speed things up considerably — if you could set me up with an account beforehand, I can test it hands-on directly, which will also make the content more relevant to what your team will actually be using.

Don't overdo it: formal doesn't mean bureaucratic. Avoid stacking jargon ("cross-functional synergy alignment deliverables"), unnecessary length, or passive voice so pervasive the sentence loses its subject. The goal is clean and sharp, not corporate-speak.
