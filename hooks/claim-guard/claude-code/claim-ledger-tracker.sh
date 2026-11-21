#!/bin/bash
# claim-ledger-tracker.sh
#
# This one works like a dashcam: every time the AI runs a command, it quietly
# logs an entry beside it — no noise, no interruption.
#
# It logs three kinds of things:
#   1. Which verification-type commands were run (tests, builds, version checks, etc.),
#      and separately which of them ran tests or a build
#   2. Which searches were performed (finding files, finding keywords, WebSearch, WebFetch)
#   3. Which files were edited, so a verification that ran before the last edit
#      doesn't count as covering the current code
#
# What gets logged is used by the neighboring claim-evidence-guard.sh, which
# checks this ledger at the end of the turn to see whether "what it just said"
# is actually backed by evidence. The two hooks must be installed together.
#
# The ledger lives in a cache folder under the user's home directory, kept
# separate per conversation, so it never pollutes your project.
#
# Subagents: Claude Code puts agent_id on a tool call made inside a subagent,
# while session_id stays the parent's. Such a call is logged twice: in the
# parent's ledger, exactly as before, and in the subagent's own
# <session>.<agent_id>.* ledger, which only that subagent's SubagentStop check
# reads and removes. A SubagentHandback call's message (the report the parent
# receives) is kept beside it as <session>.<agent_id>.report until then.
#
# Adapted from AlethiaQuizForge/no-hallucination's (MIT licensed) verify-tracker
# and search-tracker, merged into one hook with an isolated ledger path.

LEDGER_DIR="${CLAIM_GUARD_LEDGER_DIR:-$HOME/.cache/claude-guard-hooks}"

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
SID=$(echo "$INPUT" | jq -r '(.session_id // "default") | tostring | gsub("[^A-Za-z0-9._-]"; "_") | .[0:80]')
SID="${SID:-default}"

AID=$(echo "$INPUT" | jq -r '(.agent_id // "") | if type == "string" then gsub("^\\s+|\\s+$"; "") | gsub("[^A-Za-z0-9_-]"; "_") | .[0:64] else "" end' 2>/dev/null)

# log <kind> <line>: the session's ledger and, inside a subagent, that subagent's too.
log() {
    mkdir -p "$LEDGER_DIR"
    echo "$(date +%H:%M:%S) $2" >> "$LEDGER_DIR/${SID}.$1"
    if [[ -n "$AID" ]]; then
        echo "$(date +%H:%M:%S) $2" >> "$LEDGER_DIR/${SID}.${AID}.$1"
    fi
}

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

case "$TOOL" in
    Write|Edit|MultiEdit|NotebookEdit)
        FP=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')
        log edit "$TOOL ${FP:0:160}"
        ;;
    mcp__claude-in-chrome__*)
        # Driving a real browser checks live state, so it counts as verification
        log verify "$TOOL"
        ;;
    Grep|Glob)
        log search "$TOOL"
        ;;
    WebSearch)
        QUERY=$(echo "$INPUT" | jq -r '.tool_input.query // empty')
        log search "WebSearch ${QUERY:0:120}"
        ;;
    WebFetch)
        URL=$(echo "$INPUT" | jq -r '.tool_input.url // empty')
        log search "WebFetch ${URL:0:120}"
        ;;
    SubagentHandback)
        # The report a subagent hands back; its SubagentStop check reads it.
        if [[ -n "$AID" ]]; then
            MSG=$(echo "$INPUT" | jq -r '.tool_input.message // empty')
            if [[ -n "$MSG" ]]; then
                mkdir -p "$LEDGER_DIR"
                printf '%s' "${MSG:0:200000}" > "$LEDGER_DIR/${SID}.${AID}.report"
            fi
        fi
        ;;
    Bash)
        CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
        [[ -z "$CMD" ]] && exit 0
        # Verification-type: tests, builds, status, health checks, diff, lint, live-run scripts
        if echo "$CMD" | grep -qE '(--version|npm (run build|test)|pytest|jest|cargo test|go test|make test|uv run|vault-lint|visual-drift-lint|py_compile|bash -n|jq (-e |\.)|curl.*-[sI]|git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(status|diff|log)|systemctl (status|is-active)|test -[fedrwx]|grep -[qcl]|wc -[lcw]|python3 (-c|-m)|node -e|pdfinfo|cmp -s|diff -r|playwright test|agent-browser)'; then
            log verify "${CMD:0:120}"
        fi
        # Tier one: a test or build run (CLAIM_GUARD_TEST_CMD adds one more pattern)
        if printf '%s' "$CMD" | grep -qiE -- "$TEST_CMD_ERE" \
            || { [[ -n "${CLAIM_GUARD_TEST_CMD:-}" ]] && printf '%s' "$CMD" | grep -qiE -- "$CLAIM_GUARD_TEST_CMD" 2>/dev/null; }; then
            log test "${CMD:0:120}"
        fi
        # Search-type: grep/rg/find/ls/gh api lookups
        if echo "$CMD" | grep -qE '(^|[|;&][[:space:]]*)(grep|rg|find|ls|fd|gh api|mdfind)[[:space:]]'; then
            log search "${CMD:0:120}"
        fi
        ;;
    *) exit 0 ;;
esac

exit 0
