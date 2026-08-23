# Two worked examples

Both are real shapes of task, written out stage by stage. Use them as a pattern, not a
template to fill in.

## Porting something to another platform

**Research.** Compare what the two platforms actually give you, rather than what you assume
they give you. Shell versus Python, POSIX paths versus Windows paths, which interpreter a
bare command name resolves to, which dependencies exist on a stock install. Check on the
target machine; a platform difference is exactly the thing that does not show up in
documentation.

**Plan.** List the modules to port, decide what the shared interface is, and decide where
the platform branch lives. One branch point in a known place beats a dozen scattered
`if platform ==` checks.

**Build.** Prefer the standard library, so the port does not bring a dependency the target
platform lacks. Keep the judging logic identical across platforms — if the two versions
disagree about what to do, that is a bug, not a platform difference.

**Verify.** Run it on the target platform, not only on yours. A synthetic input proves the
logic; only the real platform proves the plumbing.

## Adding a guardrail hook

**Research.** Look at what actually went wrong historically, and at how a guard like this
gets bypassed in practice: quoting the argument, a different flag spelling, chaining with a
separator, wrapping in an interpreter. The bypasses are the specification.

**Plan.** Decide what gets blocked and what gets allowed, which event to hook (before the
action, or at the end of the turn), and what happens when the hook cannot read its input.
Fail open unless you can state precisely why failing closed is safe — a guard that blocks
the user out of their own session is its own kind of incident.

**Build.** Write the logic and the test cases together, including the cases that must be
*allowed*. A guard with only blocking tests will pass while being unusable.

**Verify.** Run the regression suite, then trigger it for real once and watch it block.
Those are different claims: the suite says the logic is right, the live fire says it is
installed and running.
