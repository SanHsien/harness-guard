#!/usr/bin/env bash
# Stop: block unsupported verification claims and unsupported negative assertions.
set -u

ledger_dir="$HOME/.cache/codex-guard-hooks"
input="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  printf '{}\n'
  exit 0
fi

turn_id="$(printf '%s' "$input" | jq -r '.turn_id // .session_id // "default"' 2>/dev/null)" || {
  printf '{}\n'
  exit 0
}
verify_ledger="$ledger_dir/${turn_id}.verify"
search_ledger="$ledger_dir/${turn_id}.search"
cleanup() { rm -f "$verify_ledger" "$search_ledger"; }

stop_active="$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)"
last_message="$(printf '%s' "$input" | jq -r '.last_assistant_message // empty' 2>/dev/null)"
if [ -z "$last_message" ]; then
  printf '{}\n'
  exit 0
fi

block_reason() {
  jq -n --arg reason "$1" '{decision:"block",reason:$reason}'
  exit 0
}

check_quality_summary_gate() {
  cwd="$(printf '%s' "$input" | jq -r '.cwd // .working_directory // empty' 2>/dev/null)"
  [ -n "$cwd" ] || cwd="$PWD"
  repo_root="$cwd"
  while [ "$repo_root" != "/" ]; do
    [ -f "$repo_root/loop-policy.toml" ] || [ -e "$repo_root/.git" ] && break
    parent="$(dirname "$repo_root")"
    [ "$parent" != "$repo_root" ] || break
    repo_root="$parent"
  done
  [ -f "$repo_root/loop-policy.toml" ] || return 0
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

verify_triggers='verified|confirmed|all passing|tests? pass|build passes|all green|works now|working now|deployed and verified|驗證通過|測試通過|驗證無誤|實測通過|實測有效|全數通過|建置通過|跑通|已驗證|確認無誤'
if printf '%s' "$last_message" | grep -iqE "$verify_triggers"; then
  if [ ! -s "$verify_ledger" ] && [ "$stop_active" != "true" ]; then
    cleanup
    block_reason "CLAIM-EVIDENCE GUARD: The reply claims verification or tests passed, but no verification command was recorded this turn. Verify it first or mark it as not yet verified."
  fi
  quality_error="$(check_quality_summary_gate)"
  [ -z "$quality_error" ] || block_reason "$quality_error"
fi

# A second pass relaxes only the session-ledger requirement. Machine evidence
# remains fail-closed until Full verification is current.
if [ "$stop_active" = "true" ]; then
  cleanup
  printf '{}\n'
  exit 0
fi

negative_triggers="doesn't exist|does not exist|not found|no such|couldn't find|cannot find|can't find|nothing matching|no evidence|there is no|不存在|找不到|沒有找到|查無|沒有任何(相關|紀錄|檔案)|從未出現"
if printf '%s' "$last_message" | grep -iqE "$negative_triggers" && [ ! -s "$search_ledger" ]; then
  cleanup
  jq -n '{decision:"block",reason:"CLAIM-EVIDENCE GUARD: The reply asserts something does not exist or cannot be found, but no search action was recorded this turn. Search exhaustively first before making a negative assertion."}'
  exit 0
fi

cleanup
printf '{}\n'
exit 0
