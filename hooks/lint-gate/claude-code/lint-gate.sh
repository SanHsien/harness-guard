#!/bin/bash
# lint-gate.sh
#
# This one runs a check command you specify, once, when the AI is about to
# end this turn. If there's an error, the error output is fed back to it, and
# it isn't allowed to end until it's fixed.
#
# Why this is needed: putting "remember to run the check first" in a rules
# file doesn't work. It forgets, and it doesn't tell you when it forgets. With
# this in place, "you can't leave until it passes" is enforced by the
# computer, not by its self-discipline.
#
# Only local commands run here — no AI calls, no cost.
#
# Three settings to configure, either edit them below or override with an
# environment variable of the same name at startup:
#
#   LINT_CMD       the check command to run
#   FAIL_PATTERN   if this text appears in the check output, this run failed
#   PASS_PATTERN   if this text appears, it passed. Leave empty and it means
#                  "passes as long as the failure text doesn't appear"
#
# A few examples:
#   LINT_CMD='npm run lint'        FAIL_PATTERN='[1-9][0-9]* error'
#   LINT_CMD='ruff check .'        FAIL_PATTERN='^Found [1-9]'
#   LINT_CMD='python3 lint.py'     FAIL_PATTERN='ERROR total: [1-9]'  PASS_PATTERN='ERROR total: 0'

set -uo pipefail

LINT_CMD="${LINT_CMD:-}"
FAIL_PATTERN="${FAIL_PATTERN:-[1-9][0-9]* (error|ERROR)}"
PASS_PATTERN="${PASS_PATTERN:-}"

input=$(cat)

# Do not delete this block. It asks "is this stop happening because I already
# blocked it once last round?" If so, let it through. Without this, an error
# that can't be fixed would trigger an infinite loop: try to end, get
# blocked, try to end again, get blocked again, forever.
if echo "$input" | jq -e '.stop_hook_active == true' >/dev/null 2>&1; then
  exit 0
fi

[ -n "$LINT_CMD" ] || exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

out=$(eval "$LINT_CMD" 2>&1)

# When the check command itself is broken (typo, crash, prints nothing at
# all), always let it through. A broken check tool shouldn't leave the user
# unable to ever finish.
[ -n "$out" ] || exit 0

if [ -n "$PASS_PATTERN" ]; then
  echo "$out" | grep -qE "$PASS_PATTERN" && exit 0
fi

if echo "$out" | grep -qE "$FAIL_PATTERN"; then
  {
    echo "Pre-completion check failed (${LINT_CMD}). Fix it before ending this turn:"
    echo "$out" | grep -E "$FAIL_PATTERN" | head -20
  } >&2
  exit 2
fi

exit 0
