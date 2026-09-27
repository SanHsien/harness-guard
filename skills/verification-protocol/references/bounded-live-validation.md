# Bounded Live Validation

Use this procedure for live UI, production, OAuth, deployment, or external-service
verification. These checks can mutate shared state or consume scarce quota, so evidence
must be both authoritative and intentionally bounded.

## Before the first live action

1. Read the repository runbook, agent instructions, and the latest successful evidence
   for the same kind of check. Reuse a proven route instead of rediscovering abandoned
   ones.
2. Write a minimal evidence ledger: the exact requirement, one authoritative signal for
   each layer that matters, and the condition that ends the check.
3. Choose one unique smoke-data prefix and create at most one smoke entity unless a
   second entity proves a genuinely different branch.
4. Confirm that the planned action is already within the user's authorization. A test
   plan does not grant permission to deploy, publish, delete, message people, or mutate a
   different system.

## While collecting evidence

- Query by the unique ID or prefix, a narrow time window, and only the fields needed for
  the decision. Summarize large logs locally; do not dump unfiltered tabs, logs, or
  records into the conversation.
- Take one authoritative observation per layer. For example, a successful API response
  and the resulting durable record prove different layers; repeating either one does
  not.
- If browser or tool control becomes stale, apply the documented recovery once. If the
  same method fails again, use an already-proven fallback or report the remaining gap.
  Do not loop on reinitialization or unbounded polling.
- Hand off only the OAuth or login step that requires the user. After the user completes
  it, continue from the current state instead of restarting the workflow.
- Stop immediately when every ledger item is satisfied. Record exact IDs, timestamps,
  candidate revision, or deployment version needed to tie the evidence to the thing
  being verified.

## Cleanup

If cleanup is part of the authorized task, identify the exact smoke IDs or keys first.
Where the tool or policy requires action-time confirmation, ask once for those exact
targets. Delete atomically where practical, then run one bounded query with the same
filter to prove the count returned to zero. Never broaden cleanup from the smoke entity
to surrounding user data.

If live validation cannot be completed within these bounds, report which ledger item is
still missing and mark it as not verified. Do not substitute repeated low-authority
signals for the missing evidence.
