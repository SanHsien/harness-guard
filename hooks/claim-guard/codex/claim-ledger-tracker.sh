#!/usr/bin/env bash
# PostToolUse: record verification, search and file-write actions for the current Codex turn.
# Each ledger's mtime is when that kind of event last happened; the Stop guard compares
# .edit against .verify to tell whether a verification still covers the current code.
set -u

ledger_dir="${CLAIM_GUARD_LEDGER_DIR:-$HOME/.cache/codex-guard-hooks}"
input="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  printf '{}\n'
  exit 0
fi

tool="$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null)"
turn_id="$(printf '%s' "$input" | jq -r '(.turn_id // .session_id // "default") | tostring | gsub("[^A-Za-z0-9._-]"; "_") | .[0:80]' 2>/dev/null)"
turn_id="${turn_id:-default}"
verify_ledger="$ledger_dir/${turn_id}.verify"
search_ledger="$ledger_dir/${turn_id}.search"
edit_ledger="$ledger_dir/${turn_id}.edit"
test_ledger="$ledger_dir/${turn_id}.test"

# >>> test-cmd-ere
# Tier one: commands that run tests or a build. The same list as
# TEST_BUILD_PATTERNS in windows/claim_ledger_tracker.py, in grep -E syntax;
# ShellTestTierParity in tests/run-tests.py runs both on the same commands.
# It is written to its own .test ledger and never changes what counts for .verify.
tc_s='(^|[;&|(][[:space:]]*|(npx|bunx|pnpm[[:space:]]+exec|uv[[:space:]]+run|poetry[[:space:]]+run|pipenv[[:space:]]+run|hatch[[:space:]]+run|time|exec|call)[[:space:]]+(-[^[:space:]]*[[:space:]]+)*)'
tc_p='["&[:space:]]*([^[:space:];&|]*[/\\])?'
tc_x='(\.exe|\.cmd|\.bat)?"?([[:space:]]|$)'
tc_e='([^[:alnum:]_]|$)'
tc_name='((run[-_]?)?tests?([-_.][[:alnum:]_.-]*)?|[[:alnum:]_.-]*[[:alnum:]_][-_.](tests?|spec)|(dev|ci)[-_]?check|check[-_]?all|verify[-_]?install)'
tc_dir='tests?[/\\][^[:space:];&|"]+'
tc_interp='(python[0-9.]*|py|node|bash|sh|zsh|pwsh|powershell|bun|deno|ruby|perl|php)'
TEST_CMD_ERE="${tc_s}${tc_p}(npm|pnpm|yarn|bun)${tc_x}[[:space:]]*(run[[:space:]]+)?(test|build|check|typecheck|e2e)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}deno${tc_x}[[:space:]]*(test|task)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}cargo${tc_x}[[:space:]]*(\\+[^[:space:]]+[[:space:]]+)?(test|build|check|nextest|clippy)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}go${tc_x}[[:space:]]*(test|build|vet)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}dotnet${tc_x}[[:space:]]*(test|build)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}(mvnw?|gradlew?)${tc_x}[^|;&]*(test|build|verify|check|package)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}make${tc_x}([[:space:]]*-[^[:space:]]+)*[[:space:]]*(test|check|build|all)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}playwright${tc_x}[[:space:]]*test${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}node${tc_x}([[:space:]]*-[^[:space:]]+)*[[:space:]]*--test${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}cmake${tc_x}[[:space:]]*--build${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}(pytest|py\\.test|jest|vitest|mocha|tsc|tox|nox|ctest|msbuild|phpunit|rspec)${tc_x}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}(bash|sh|zsh)${tc_x}[[:space:]]*-n${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}${tc_interp}(\\.exe|\\.cmd|\\.bat)?\"?[[:space:]]([^|;&]*[[:space:]/\\\\\"=])?(${tc_name}\\.(py|ps1|sh|js|mjs|cjs|ts|bat|cmd)|${tc_dir}\\.(py|ps1|sh|js|mjs|cjs|ts))${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|${tc_s}${tc_p}(${tc_name}\\.(ps1|sh|bat|cmd|py)|${tc_dir}\\.(ps1|sh|bat|cmd))${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|-m[[:space:]]+(pytest|unittest|compileall|py_compile|doctest)${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|(^|[^[:alnum:]_])py_compile${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|(^|[^[:alnum:]_-])Invoke-Pester${tc_e}"
TEST_CMD_ERE="$TEST_CMD_ERE|(^|[^[:alnum:]_])gh[[:space:]]+(run[[:space:]]+(view|watch|list)|pr[[:space:]]+checks)${tc_e}"
# <<< test-cmd-ere

case "$tool" in
  apply_patch|Write|Edit|MultiEdit|NotebookEdit)
    fp="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)"
    mkdir -p "$ledger_dir"
    printf '%s %s %.160s\n' "$(date +%H:%M:%S)" "$tool" "$fp" >> "$edit_ledger"
    ;;
  Grep|Glob)
    mkdir -p "$ledger_dir"
    printf '%s %s\n' "$(date +%H:%M:%S)" "$tool" >> "$search_ledger"
    ;;
  WebSearch)
    query_text="$(printf '%s' "$input" | jq -r '.tool_input.query // empty' 2>/dev/null)"
    mkdir -p "$ledger_dir"
    printf '%s WebSearch %.120s\n' "$(date +%H:%M:%S)" "$query_text" >> "$search_ledger"
    ;;
  web_fetch|WebFetch)
    url_text="$(printf '%s' "$input" | jq -r '.tool_input.url // empty' 2>/dev/null)"
    mkdir -p "$ledger_dir"
    printf '%s WebFetch %.120s\n' "$(date +%H:%M:%S)" "$url_text" >> "$search_ledger"
    ;;
  Bash|Exec|exec|exec_command|shell|shell_command|run_command|Shell)
    command_text="$(printf '%s' "$input" | jq -r '.tool_input.command // .tool_input.CommandLine // .tool_input.cmd // .command // empty' 2>/dev/null)"
    if [ -n "$command_text" ]; then
      if printf '%s' "$command_text" | grep -qE '(--version|npm (run build|test)|pytest|jest|cargo test|go test|make test|uv run|vault-lint|visual-drift-lint|py_compile|bash -n|jq (-e |\.)|curl.*-[sI]|git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(status|diff|log)|systemctl (status|is-active)|test -[fedrwx]|grep -[qcl]|wc -[lcw]|python3 (-c|-m)|node -e|pdfinfo|cmp -s|diff -r|playwright test|agent-browser)'; then
        mkdir -p "$ledger_dir"
        printf '%s %.120s\n' "$(date +%H:%M:%S)" "$command_text" >> "$verify_ledger"
      fi
      # Tier one: a test or build run (CLAIM_GUARD_TEST_CMD adds one more pattern)
      if printf '%s' "$command_text" | grep -qiE -- "$TEST_CMD_ERE" \
          || { [ -n "${CLAIM_GUARD_TEST_CMD:-}" ] && printf '%s' "$command_text" | grep -qiE -- "$CLAIM_GUARD_TEST_CMD" 2>/dev/null; }; then
        mkdir -p "$ledger_dir"
        printf '%s %.120s\n' "$(date +%H:%M:%S)" "$command_text" >> "$test_ledger"
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
