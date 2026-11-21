#!/bin/bash
# claim-evidence-guard.sh
#
# This one runs when the AI is about to end this turn, and reconciles the
# ledger against what was said.
#
# It checks two things:
#   1. It claimed "I tested it" / "verification passed" / "confirmed working"
#      → the ledger must have a real record of a verification command being run,
#        and no file may have been edited after the last one (that verification
#        did not cover the code as it is now)
#   2. It claimed "not found" / "doesn't exist"
#      → the ledger must have a real record of a search being performed
# If it doesn't add up, the turn is blocked from ending, and it's told what's
# missing.
#
# The ledger is written by the neighboring claim-ledger-tracker.sh — the two
# must be installed together, or this one stops working.
#
# Why this is needed: saying "I tested it" costs the AI almost nothing. It can
# say that in exactly the same tone whether or not it actually ran anything,
# and you can't tell the difference. Rather than trust the claim, check the
# record.
#
# Only small local commands run here — no AI calls, no cost.
#
# When the data can't be read or the format is wrong, it always lets the turn
# through — better to miss a block than to block wrongly. It only intervenes
# when the claim was made explicitly AND the ledger has zero matching records.
#
# Adapted from AlethiaQuizForge/no-hallucination's (MIT licensed) verify-guard
# and claim-guard, merged into one hook with Chinese trigger phrases added.

LEDGER_DIR="${CLAIM_GUARD_LEDGER_DIR:-$HOME/.cache/claude-guard-hooks}"

INPUT=$(cat)
SID=$(echo "$INPUT" | jq -r '(.session_id // "default") | tostring | gsub("[^A-Za-z0-9._-]"; "_") | .[0:80]' 2>/dev/null) || exit 0
SID="${SID:-default}"

VERIFY_LEDGER="$LEDGER_DIR/${SID}.verify"
SEARCH_LEDGER="$LEDGER_DIR/${SID}.search"
EDIT_LEDGER="$LEDGER_DIR/${SID}.edit"
TEST_LEDGER="$LEDGER_DIR/${SID}.test"

cleanup() { rm -f "$VERIFY_LEDGER" "$SEARCH_LEDGER" "$EDIT_LEDGER" "$TEST_LEDGER"; }

# >>> test-claim-ere
# Tier two of a verification claim: "tests pass" / "the build passes" wants a
# test or build run (the tracker's .test ledger), not only status queries. Same
# words as TEST_CLAIM_TRIGGERS / TEST_CLAIM_NOT in windows/claim_evidence_guard.py.
# A notice (systemMessage), never a block: see that file for the measurement.
TEST_CLAIM_ERE='tests? pass|all passing|build passes|all green|測試通過|建置通過|全數通過|所有測試已通過|全部測試通過|編譯成功|建置成功'
TEST_CLAIM_NOT_SED='s/(^|[^[:alnum:]_])([Oo][Nn][Cc][Ee]|[Ii][Ff]|[Uu][Nn][Tt][Ii][Ll]|[Ww][Hh][Ee][Nn]|[Aa][Ff][Tt][Ee][Rr]|[Bb][Ee][Ff][Oo][Rr][Ee]|[Uu][Nn][Ll][Ee][Ss][Ss])[[:space:]]+(([Aa][Ll][Ll]|[Tt][Hh][Ee])[[:space:]]+)*[Tt][Ee][Ss][Tt][Ss]?[[:space:]]+[Pp][Aa][Ss][Ss]/\1 /g; s/測試通過(後|之後|再|才)/ /g; s/(等到|等|待|直到)(全部)?測試通過/ /g'
# <<< test-claim-ere

NOTICE=""
test_tier_notice() {
    printf '%s' "$LAST_MSG" | sed -E "$TEST_CLAIM_NOT_SED" | grep -iqE -- "$TEST_CLAIM_ERE" || return 0
    if [[ ! -s "$TEST_LEDGER" ]]; then
        local last_verify
        last_verify=$(tail -1 "$VERIFY_LEDGER" 2>/dev/null)
        printf 'CLAIM-EVIDENCE GUARD (notice): you said tests or a build pass, but no test or build command ran this turn -- only status queries such as git status, ls or Test-Path.\n  Last verification: %s\nIf the tests ran in an earlier turn or in another agent, say where; otherwise run them before saying they pass.' "${last_verify:-(none)}"
    elif [[ -s "$EDIT_LEDGER" && "$EDIT_LEDGER" -nt "$TEST_LEDGER" ]]; then
        printf 'CLAIM-EVIDENCE GUARD (notice): you said tests or a build pass, but files were edited after the last test or build run, so it did not cover the current code.\n  Last test run: %s\n  Later edit: %s' "$(tail -1 "$TEST_LEDGER")" "$(tail -1 "$EDIT_LEDGER")"
    fi
}

# Let the turn end, showing the notice (if any) to the user as a systemMessage.
allow() {
    cleanup
    if [[ -n "$NOTICE" ]]; then
        printf '%s\n' "$NOTICE" >&2
        jq -n --arg m "$NOTICE" '{systemMessage:$m}'
    fi
    exit 0
}

# Trigger words (English + Chinese), shared by the Stop and the SubagentStop check.
VERIFY_TRIGGERS='verified|confirmed|all passing|tests? pass|build passes|all green|works now|working now|deployed and verified|驗證通過|測試通過|驗證無誤|實測通過|實測有效|全數通過|建置通過|跑通|已驗證|確認無誤'
NEG_TRIGGERS="doesn't exist|does not exist|not found|no such|couldn't find|cannot find|can't find|nothing matching|no evidence|there is no|不存在|找不到|沒有找到|查無|沒有任何(相關|紀錄|檔案)|從未出現"

# Negations ("not yet verified") and code identifiers (`is_verified`, `confirmed()`)
# contain a trigger word without claiming it; drop them before matching. Quoted
# text is kept: wrapping a claim in `...` or 「...」 must not get it past the guard.
# Same pattern as NOT_A_CLAIM in windows/claim_evidence_guard.py.
# jq's regex is Unicode-aware whatever the locale; if it fails, the full message is kept.
strip_not_a_claim() {
    jq -Rrs 'gsub("(?:\\bun|\\bnot (?:yet )?|n\\Wt (?:yet )?|\\bnever |\\b[A-Za-z0-9]*_|(?<![^\\s`(])--)(?:verified|confirmed)|(?:verified|confirmed)(?:_|\\(\\))|(?<=[/`])(?:verified|confirmed)(?-i:\\.(?:py|js|ts|tsx|md|json|sh|txt|ya?ml|toml|rs|go|java|rb))\\b"; " "; "i")' 2>/dev/null
}

# -- SubagentStop ----------------------------------------------------------------
# A subagent's report is checked against the subagent's own ledger,
# <session>.<agent_id>.* (see claim-ledger-tracker.sh). Every finding is a notice
# (systemMessage), never a block: windows/claim_evidence_guard.py has the
# measurement. Only that subagent's ledger is removed; the parent's is not read
# and not touched, so the parent's Stop check below is exactly what it was.
# A subagent ledger nobody collected is removed once it has been idle for a day.
find "$LEDGER_DIR" -maxdepth 1 -type f -name "${SID}.*.*" -mmin +1440 \
    \( -name '*.verify' -o -name '*.search' -o -name '*.edit' -o -name '*.test' -o -name '*.report' \) \
    -delete 2>/dev/null

subagent_stop() {
    local aid atype active stem v s e t report text atp last stripped who found=""
    aid=$(echo "$INPUT" | jq -r '(.agent_id // "") | if type == "string" then gsub("^\\s+|\\s+$"; "") | gsub("[^A-Za-z0-9_-]"; "_") | .[0:64] else "" end' 2>/dev/null)
    [[ -n "$aid" ]] || exit 0
    stem="$LEDGER_DIR/${SID}.${aid}"
    v="$stem.verify"; s="$stem.search"; e="$stem.edit"; t="$stem.test"; report="$stem.report"
    # Claude Code also fires SubagentStop for its own internal agents (prompt
    # suggestions, /btw); in a session without --agent those have an empty type.
    atype=$(echo "$INPUT" | jq -r 'if .agent_type == "" then "-" else (.agent_type // "unnamed" | tostring) end' 2>/dev/null)
    active=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
    if [[ "$atype" != "-" && "$active" != "true" ]]; then
        # The report: the SubagentHandback message if the subagent used that tool
        # (kept by the tracker, else read from the subagent's transcript), plus
        # its last message.
        text=$(cat "$report" 2>/dev/null)
        if [[ -z "${text//[[:space:]]/}" ]]; then
            atp=$(echo "$INPUT" | jq -r '.agent_transcript_path // empty' 2>/dev/null)
            atp="${atp/#\~/$HOME}"
            if [[ -n "$atp" && -r "$atp" ]]; then
                text=$(tail -c 512000 "$atp" | jq -Rrs '[split("\n")[] | (try fromjson catch empty) | select(type == "object") | .message | select(type == "object") | .content | select(type == "array") | .[] | select(type == "object" and .type == "tool_use" and .name == "SubagentHandback") | .input | select(type == "object") | .message | select(type == "string")] | last // empty' 2>/dev/null)
            fi
        fi
        last=$(echo "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
        text="$text
$last"
        if stripped=$(printf '%s' "$text" | strip_not_a_claim); then
            text=$stripped
        fi
        who="$atype ($aid)"
        sub_note() {
            found="${found:+$found

}CLAIM-EVIDENCE GUARD (subagent notice): subagent $who $1"
        }
        if printf '%s' "$text" | grep -iqE "$VERIFY_TRIGGERS"; then
            if [[ ! -s "$v" ]]; then
                sub_note "reported 'verified / tests pass / confirmed', but its own ledger has no verification command (test, build, status, diff, live run).
Missing evidence: any verification command run by that subagent. Treat the report as not yet verified until someone checks it."
            elif [[ -s "$e" && "$e" -nt "$v" ]]; then
                sub_note "reported 'verified / tests pass / confirmed', but it edited files after its last verification command, so that run did not cover what it handed back.
  Last verification: $(tail -1 "$v")
  Later edit: $(tail -1 "$e")
Missing evidence: a verification run after that edit."
            elif printf '%s' "$text" | sed -E "$TEST_CLAIM_NOT_SED" | grep -iqE -- "$TEST_CLAIM_ERE"; then
                if [[ ! -s "$t" ]]; then
                    sub_note "said tests or a build pass, but its own ledger has no test or build command -- only status queries such as git status, ls or Test-Path.
  Last verification: $(tail -1 "$v")
Missing evidence: a test or build run by that subagent."
                elif [[ -s "$e" && "$e" -nt "$t" ]]; then
                    sub_note "said tests or a build pass, but it edited files after its last test or build run.
  Last test run: $(tail -1 "$t")
  Later edit: $(tail -1 "$e")
Missing evidence: a test or build run after that edit."
                fi
            fi
        fi
        if printf '%s' "$text" | grep -iqE "$NEG_TRIGGERS" && [[ ! -s "$s" ]]; then
            sub_note "asserted something 'does not exist / cannot be found', but its own ledger has no search (Grep/Glob/find/ls/Select-String/WebSearch).
Missing evidence: a search by that subagent."
        fi
    fi
    rm -f "$v" "$s" "$e" "$t" "$report"
    if [[ -n "$found" ]]; then
        printf '%s\n' "$found" >&2
        jq -n --arg m "$found" '{systemMessage:$m}'
    fi
    exit 0
}

# A subagent finishing is not the session finishing: it must never reach the
# code below, which empties the session's ledger.
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null)
if [[ "$EVENT" == "SubagentStop" ]]; then
    subagent_stop
fi

STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
[[ -z "$LAST_MSG" ]] && exit 0
if STRIPPED=$(printf '%s' "$LAST_MSG" | strip_not_a_claim); then
    LAST_MSG=$STRIPPED
fi

block_reason() {
    jq -n --arg reason "$1" '{decision:"block",reason:$reason}'
    exit 0
}

check_quality_summary_gate() {
    local cwd repo_root parent
    cwd=$(echo "$INPUT" | jq -r '.cwd // .working_directory // empty' 2>/dev/null)
    [[ -n "$cwd" ]] || cwd=$PWD
    repo_root=$cwd
    while [[ "$repo_root" != "/" ]]; do
        [[ -f "$repo_root/loop-policy.toml" || -e "$repo_root/.git" ]] && break
        parent=$(dirname "$repo_root")
        [[ "$parent" != "$repo_root" ]] || break
        repo_root=$parent
    done
    [[ -f "$repo_root/loop-policy.toml" ]] || return 0
    if ! command -v python3 >/dev/null 2>&1; then
        printf '%s\n' "CLAIM-EVIDENCE GUARD: Python 3 is required to validate machine evidence."
        return 0
    fi
    python3 - "$repo_root" <<'PY'
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

root = Path(sys.argv[1])
policy_file = root / "loop-policy.toml"
summary_file = root / "artifacts" / "quality-summary.json"
try:
    policy = tomllib.loads(policy_file.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"CLAIM-EVIDENCE GUARD: 'loop-policy.toml' is unreadable: {exc}")
    raise SystemExit
verification = policy.get("verification", {})
if not isinstance(verification, dict) or verification.get("require_machine_evidence") is not True:
    raise SystemExit
if not summary_file.exists():
    print("CLAIM-EVIDENCE GUARD: Target repository requires machine evidence, but "
          "'artifacts/quality-summary.json' does not exist. Run Full verification first.")
    raise SystemExit
try:
    data = json.loads(summary_file.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"CLAIM-EVIDENCE GUARD: 'artifacts/quality-summary.json' is unreadable: {exc}")
    raise SystemExit
if not isinstance(data, dict):
    print("CLAIM-EVIDENCE GUARD: Quality summary must be a JSON object.")
    raise SystemExit
if data.get("schema_version") != 1:
    print("CLAIM-EVIDENCE GUARD: Quality summary schema_version must be 1.")
    raise SystemExit
if data.get("profile") != "full":
    print("CLAIM-EVIDENCE GUARD: Quality summary profile must be 'full'.")
    raise SystemExit
gates = data.get("gates")
if not isinstance(gates, dict) or not gates:
    print("CLAIM-EVIDENCE GUARD: Quality summary gates must be a non-empty object.")
    raise SystemExit
if any(not isinstance(value, bool) for value in gates.values()):
    print("CLAIM-EVIDENCE GUARD: Every quality summary gate must be boolean.")
    raise SystemExit
if data.get("passed") is not True or not all(gates.values()):
    print("CLAIM-EVIDENCE GUARD: Quality summary indicates gate failure.")
    raise SystemExit
commit = data.get("commit")
if not isinstance(commit, str) or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit) is None:
    print("CLAIM-EVIDENCE GUARD: Quality summary commit must be a full Git object id.")
    raise SystemExit
head = subprocess.run(
    ["git", "rev-parse", "--verify", "HEAD"],
    cwd=root,
    capture_output=True,
    text=True,
    check=False,
)
if head.returncode != 0 or not head.stdout.strip():
    print("CLAIM-EVIDENCE GUARD: Current git HEAD could not be resolved.")
elif head.stdout.strip().lower() != commit.lower():
    print("CLAIM-EVIDENCE GUARD: Quality summary commit does not match current git HEAD.")
PY
}

# A) Verification claims (English + Chinese)
if echo "$LAST_MSG" | grep -iqE "$VERIFY_TRIGGERS"; then
    if [[ ! -s "$VERIFY_LEDGER" && "$STOP_ACTIVE" != "true" ]]; then
        cleanup
        block_reason "CLAIM-EVIDENCE GUARD: You claimed verification or tests passed, but this session's ledger has no verification command. Verify it first or mark it as not yet verified."
    fi
    # Stale verification: files were edited after the last verification command
    if [[ "$STOP_ACTIVE" != "true" && -s "$EDIT_LEDGER" && "$EDIT_LEDGER" -nt "$VERIFY_LEDGER" ]]; then
        LAST_EDIT=$(tail -1 "$EDIT_LEDGER"); LAST_VERIFY=$(tail -1 "$VERIFY_LEDGER")
        cleanup
        block_reason "CLAIM-EVIDENCE GUARD (stale verification): you claimed verified / tests pass, but files were edited after the last verification command, so it did not cover the current code.
  Last verification: $LAST_VERIFY
  Later edit: $LAST_EDIT
Re-run the verification before claiming it; if this change needs no test (docs, comments), say edited, not re-verified."
    fi
    QUALITY_ERROR=$(check_quality_summary_gate)
    [[ -z "$QUALITY_ERROR" ]] || block_reason "$QUALITY_ERROR"
    NOTICE=$(test_tier_notice)
fi

# A second pass relaxes only the session-ledger requirement. Machine evidence
# remains fail-closed until Full verification is current.
if [[ "$STOP_ACTIVE" == "true" ]]; then
    allow
fi

# B) Negative existence assertions (English + Chinese)
if echo "$LAST_MSG" | grep -iqE "$NEG_TRIGGERS"; then
    if [[ ! -s "$SEARCH_LEDGER" ]]; then
        cleanup
        cat << 'EOF'
{
  "decision": "block",
  "reason": "CLAIM-EVIDENCE GUARD: You asserted something 'doesn't exist / can't be found', but this session's ledger has no record of any search action (Grep/Glob/find/ls). A negative assertion requires an exhaustive search first — search, then say it doesn't exist."
}
EOF
        exit 0
    fi
fi

allow
