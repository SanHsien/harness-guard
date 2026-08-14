#!/usr/bin/env bash
# lint-gate.sh (Codex version)
#
# Runs a check command you specify, once, before the turn ends. If it fails,
# the turn is blocked from ending as-is.
#
# The only three differences from the Claude Code version — the decision
# logic is otherwise identical:
#   1. There's no CLAUDE_PROJECT_DIR environment variable, so cwd from stdin
#      is used instead
#   2. When letting the turn through, it must print an empty JSON object {},
#      it can't just quietly exit like the Claude Code version
#   3. Blocking returns {"decision":"block","reason":...}, not exit 2 plus stderr
#
# Hooked to the Stop event. Configure what to run via environment variables:
#
#   LINT_CMD      the command to run. If unset, the whole hook is skipped
#                 (does nothing by default, won't get in your way)
#   FAIL_PATTERN  if this pattern appears in the output, it's a failure.
#                 Defaults to matching "N error(s)"
#   PASS_PATTERN  if this pattern appears in the output, it's an immediate
#                 pass, taking priority over FAIL_PATTERN
#
# Example (in the Stop section of ~/.codex/hooks.json):
#   LINT_CMD='npm run lint' FAIL_PATTERN='[1-9][0-9]* error' .../lint-gate.sh
#
# This isn't limited to code. Any command that "produces a result you can
# tell success or failure from" works — for example a doc link checker, a
# spell checker, or a data integrity script.

set -uo pipefail

LINT_CMD="${LINT_CMD:-}"
FAIL_PATTERN="${FAIL_PATTERN:-[1-9][0-9]* (error|ERROR)}"
PASS_PATTERN="${PASS_PATTERN:-}"

input="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  printf '{}\n'
  exit 0
fi

# Already blocked once by this hook — don't loop forever
stop_active="$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)"
if [ "$stop_active" = "true" ]; then
  printf '{}\n'
  exit 0
fi

# Nothing configured to run — do nothing
if [ -z "$LINT_CMD" ]; then
  printf '{}\n'
  exit 0
fi

# Claude Code has CLAUDE_PROJECT_DIR, Codex doesn't — read cwd from the payload instead
project_dir="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)"
[ -n "$project_dir" ] || project_dir="$(pwd)"
cd "$project_dir" 2>/dev/null || {
  printf '{}\n'
  exit 0
}

out="$(eval "$LINT_CMD" 2>&1)"
if [ -z "$out" ]; then
  printf '{}\n'
  exit 0
fi

if [ -n "$PASS_PATTERN" ] && printf '%s' "$out" | grep -qE "$PASS_PATTERN"; then
  printf '{}\n'
  exit 0
fi

if printf '%s' "$out" | grep -qE "$FAIL_PATTERN"; then
  detail="$(printf '%s' "$out" | grep -E "$FAIL_PATTERN" | head -20)"
  jq -n --arg cmd "$LINT_CMD" --arg detail "$detail" \
    '{decision:"block",reason:("LINT GATE: Pre-completion check failed (" + $cmd + "). Fix it before ending this turn:\n" + $detail)}'
  exit 0
fi

printf '{}\n'
exit 0
