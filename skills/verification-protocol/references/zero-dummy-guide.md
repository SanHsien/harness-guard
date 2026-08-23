# Fake fixes, and what to do instead

A fake fix makes the error stop appearing without making the problem stop existing. It is
worse than the failure it replaces: the failing test was telling you something, and now
nothing is.

Three shapes cover almost all of them.

## Swallowing the exception

```python
try:
    fetch_data()
except Exception:
    pass  # now it "works"
```

The call still fails. You have only removed the report. Whatever depended on that data now
gets nothing, and the next person debugging it starts from a program that appears healthy.

Instead: find out why it raised — network, authentication, a schema that changed — then
catch that specific exception and do something real with it. Retry, fall back with a log
line that says so, or let it propagate. All three are honest; `pass` is not.

## Weakening the assertion

```python
# assert result == 42
assert result is not None   # the real one was too hard to pass
```

The test now passes for any wrong answer that happens to be an object. You have kept the
ceremony of a test and thrown away the check.

Instead: fix the computation until `result == 42` is true. If 42 turns out to be the wrong
expectation, change it deliberately and say why in the commit — that is a different act
from quietly loosening it because it was red.

## The placeholder that ships

```typescript
function calculateTax(amount: number) {
    // TODO: implement later
    return 0;
}
```

This one is the most expensive, because it is silent and plausible. Every caller gets a
tax of zero and nothing anywhere reports an error.

Instead: implement it, including the edge cases. If it genuinely cannot be finished now,
make it fail loudly — throw, or return an explicit "not implemented" the caller has to
handle — so the gap is visible while it exists.

## The common thread

Ask one question before any change that makes a test go green: **does this make the
program more correct, or only more quiet?** If it is the second, it is a fake fix, whatever
it is called in the commit message.
