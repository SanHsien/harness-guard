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
# Adapted from AlethiaQuizForge/no-hallucination's (MIT licensed) verify-tracker
# and search-tracker, merged into one hook with an isolated ledger path.

LEDGER_DIR="${CLAIM_GUARD_LEDGER_DIR:-$HOME/.cache/claude-guard-hooks}"

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
SID=$(echo "$INPUT" | jq -r '(.session_id // "default") | tostring | gsub("[^A-Za-z0-9._-]"; "_") | .[0:80]')
SID="${SID:-default}"

VERIFY_LEDGER="$LEDGER_DIR/${SID}.verify"
SEARCH_LEDGER="$LEDGER_DIR/${SID}.search"
EDIT_LEDGER="$LEDGER_DIR/${SID}.edit"
TEST_LEDGER="$LEDGER_DIR/${SID}.test"

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
        mkdir -p "$LEDGER_DIR"
        echo "$(date +%H:%M:%S) $TOOL ${FP:0:160}" >> "$EDIT_LEDGER"
        ;;
    mcp__claude-in-chrome__*)
        # Driving a real browser checks live state, so it counts as verification
        mkdir -p "$LEDGER_DIR"
        echo "$(date +%H:%M:%S) $TOOL" >> "$VERIFY_LEDGER"
        ;;
    Grep|Glob)
        mkdir -p "$LEDGER_DIR"
        echo "$(date +%H:%M:%S) $TOOL" >> "$SEARCH_LEDGER"
        ;;
    WebSearch)
        QUERY=$(echo "$INPUT" | jq -r '.tool_input.query // empty')
        mkdir -p "$LEDGER_DIR"
        echo "$(date +%H:%M:%S) WebSearch ${QUERY:0:120}" >> "$SEARCH_LEDGER"
        ;;
    WebFetch)
        URL=$(echo "$INPUT" | jq -r '.tool_input.url // empty')
        mkdir -p "$LEDGER_DIR"
        echo "$(date +%H:%M:%S) WebFetch ${URL:0:120}" >> "$SEARCH_LEDGER"
        ;;
    Bash)
        CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
        [[ -z "$CMD" ]] && exit 0
        # Verification-type: tests, builds, status, health checks, diff, lint, live-run scripts
        if echo "$CMD" | grep -qE '(--version|npm (run build|test)|pytest|jest|cargo test|go test|make test|uv run|vault-lint|visual-drift-lint|py_compile|bash -n|jq (-e |\.)|curl.*-[sI]|git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(status|diff|log)|systemctl (status|is-active)|test -[fedrwx]|grep -[qcl]|wc -[lcw]|python3 (-c|-m)|node -e|pdfinfo|cmp -s|diff -r|playwright test|agent-browser)'; then
            mkdir -p "$LEDGER_DIR"
            echo "$(date +%H:%M:%S) ${CMD:0:120}" >> "$VERIFY_LEDGER"
        fi
        # Tier one: a test or build run (CLAIM_GUARD_TEST_CMD adds one more pattern)
        if printf '%s' "$CMD" | grep -qiE -- "$TEST_CMD_ERE" \
            || { [[ -n "${CLAIM_GUARD_TEST_CMD:-}" ]] && printf '%s' "$CMD" | grep -qiE -- "$CLAIM_GUARD_TEST_CMD" 2>/dev/null; }; then
            mkdir -p "$LEDGER_DIR"
            echo "$(date +%H:%M:%S) ${CMD:0:120}" >> "$TEST_LEDGER"
        fi
        # Search-type: grep/rg/find/ls/gh api lookups
        if echo "$CMD" | grep -qE '(^|[|;&][[:space:]]*)(grep|rg|find|ls|fd|gh api|mdfind)[[:space:]]'; then
            mkdir -p "$LEDGER_DIR"
            echo "$(date +%H:%M:%S) ${CMD:0:120}" >> "$SEARCH_LEDGER"
        fi
        ;;
    *) exit 0 ;;
esac

exit 0
