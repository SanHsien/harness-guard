#!/bin/bash
# claim-evidence-guard.sh
#
# This one runs when the AI is about to end this turn, and reconciles the
# ledger against what was said.
#
# It checks two things:
#   1. It claimed "I tested it" / "verification passed" / "confirmed working"
#      → the ledger must have a real record of a verification command being run
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

LEDGER_DIR="$HOME/.cache/claude-guard-hooks"

INPUT=$(cat)
SID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null) || exit 0

VERIFY_LEDGER="$LEDGER_DIR/${SID}.verify"
SEARCH_LEDGER="$LEDGER_DIR/${SID}.search"

cleanup() { rm -f "$VERIFY_LEDGER" "$SEARCH_LEDGER"; }

STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
[[ -z "$LAST_MSG" ]] && exit 0

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
VERIFY_TRIGGERS='verified|confirmed|all passing|tests? pass|build passes|all green|works now|working now|deployed and verified|驗證通過|測試通過|驗證無誤|實測通過|實測有效|全數通過|建置通過|跑通|已驗證|確認無誤'
if echo "$LAST_MSG" | grep -iqE "$VERIFY_TRIGGERS"; then
    if [[ ! -s "$VERIFY_LEDGER" && "$STOP_ACTIVE" != "true" ]]; then
        cleanup
        block_reason "CLAIM-EVIDENCE GUARD: You claimed verification or tests passed, but this session's ledger has no verification command. Verify it first or mark it as not yet verified."
    fi
    QUALITY_ERROR=$(check_quality_summary_gate)
    [[ -z "$QUALITY_ERROR" ]] || block_reason "$QUALITY_ERROR"
fi

# A second pass relaxes only the session-ledger requirement. Machine evidence
# remains fail-closed until Full verification is current.
if [[ "$STOP_ACTIVE" == "true" ]]; then
    cleanup
    exit 0
fi

# B) Negative existence assertions (English + Chinese)
NEG_TRIGGERS="doesn't exist|does not exist|not found|no such|couldn't find|cannot find|can't find|nothing matching|no evidence|there is no|不存在|找不到|沒有找到|查無|沒有任何(相關|紀錄|檔案)|從未出現"
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

cleanup
exit 0
