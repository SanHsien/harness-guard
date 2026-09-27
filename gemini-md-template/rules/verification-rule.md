# Verification: change it, then prove it

After adding or changing code, run the project's check — tests, build, or lint — before
reporting anything. The exit code is the evidence; reading the diff is not.

Never say "fixed", "done", or "tests pass" without having run the thing that produced that
result. If it genuinely can't be checked automatically, say "not verified, needs manual
confirmation" and name what needs confirming. That answer is always available.

When a check fails, read the whole stack trace and fix the cause. None of these are fixes:

- commenting out the failing case or the assertion
- swallowing the exception (`except Exception: pass`, empty `catch`)
- returning hardcoded or dummy data so the caller stops complaining

Each one converts a visible failure into an invisible one, which is worse than the failure
you started with.

When fixing a bug, check that the fix didn't break something adjacent, and add a regression
test where the project has somewhere to put one.
