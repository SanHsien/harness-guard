#!/usr/bin/env bash
# PostToolUse: record verification and search actions for the current Codex turn.
set -u

ledger_dir="$HOME/.cache/codex-guard-hooks"
input="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  printf '{}\n'
  exit 0
fi

tool="$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null)"
turn_id="$(printf '%s' "$input" | jq -r '.turn_id // .session_id // "default"' 2>/dev/null)"
verify_ledger="$ledger_dir/${turn_id}.verify"
search_ledger="$ledger_dir/${turn_id}.search"

case "$tool" in
  Grep|Glob)
    mkdir -p "$ledger_dir"
    printf '%s %s\n' "$(date +%H:%M:%S)" "$tool" >> "$search_ledger"
    ;;
  Bash|Exec|exec|exec_command|shell|shell_command|run_command|Shell)
    command_text="$(printf '%s' "$input" | jq -r '.tool_input.command // .tool_input.CommandLine // .tool_input.cmd // .command // empty' 2>/dev/null)"
    if [ -n "$command_text" ]; then
      if printf '%s' "$command_text" | grep -qE '(--version|npm (run build|test)|pytest|jest|cargo test|go test|make test|uv run|vault-lint|visual-drift-lint|py_compile|bash -n|jq (-e |\.)|curl.*-[sI]|git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(status|diff|log)|systemctl (status|is-active)|test -[fedrwx]|grep -[qcl]|wc -[lcw]|python3 (-c|-m)|node -e|pdfinfo|cmp -s|diff -r)'; then
        mkdir -p "$ledger_dir"
        printf '%s %.120s\n' "$(date +%H:%M:%S)" "$command_text" >> "$verify_ledger"
      fi
      if printf '%s' "$command_text" | grep -qE '(^|[|;&][[:space:]]*)(grep|rg|find|ls|fd|gh api|mdfind)[[:space:]]'; then
        mkdir -p "$ledger_dir"
        printf '%s %.120s\n' "$(date +%H:%M:%S)" "$command_text" >> "$search_ledger"
      fi
    fi
    ;;
esac

printf '{}\n'
exit 0
