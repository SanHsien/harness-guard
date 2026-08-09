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
if [ "$stop_active" = "true" ]; then
  cleanup
  printf '{}\n'
  exit 0
fi

last_message="$(printf '%s' "$input" | jq -r '.last_assistant_message // empty' 2>/dev/null)"
if [ -z "$last_message" ]; then
  printf '{}\n'
  exit 0
fi

verify_triggers='verified|confirmed|all passing|tests? pass|build passes|all green|works now|working now|deployed and verified|驗證通過|測試通過|驗證無誤|實測通過|實測有效|全數通過|建置通過|跑通|已驗證|確認無誤'
if printf '%s' "$last_message" | grep -iqE "$verify_triggers" && [ ! -s "$verify_ledger" ]; then
  cleanup
  jq -n '{decision:"block",reason:"CLAIM-EVIDENCE GUARD：回覆宣稱已驗證或測試通過，但本 turn 沒有驗證類指令紀錄。請先實際驗證；無法自動驗證時，明確標為尚未驗證。"}'
  exit 0
fi

negative_triggers="doesn't exist|does not exist|not found|no such|couldn't find|cannot find|can't find|nothing matching|no evidence|there is no|不存在|找不到|沒有找到|查無|沒有任何(相關|紀錄|檔案)|從未出現"
if printf '%s' "$last_message" | grep -iqE "$negative_triggers" && [ ! -s "$search_ledger" ]; then
  cleanup
  jq -n '{decision:"block",reason:"CLAIM-EVIDENCE GUARD：回覆斷言某物不存在或找不到，但本 turn 沒有搜尋動作紀錄。請先全量搜尋再下負向斷言。"}'
  exit 0
fi

cleanup
printf '{}\n'
exit 0
