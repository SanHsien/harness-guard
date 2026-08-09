#!/usr/bin/env bash
# lint-gate.sh（Codex 版）
#
# 收工前跑一次你指定的檢查指令。有錯就擋下來，不讓這一輪就這樣結束。
#
# 跟 Claude Code 版的差別只有三處，判斷邏輯一模一樣：
#   1. 沒有 CLAUDE_PROJECT_DIR 這個環境變數，改用 stdin 傳進來的 cwd
#   2. 放行時要印一個空的 JSON 物件 {}，不能像 Claude Code 那樣安靜結束
#   3. 擋下來是回 {"decision":"block","reason":...}，不是 exit 2 加 stderr
#
# 掛在 Stop 事件。用環境變數設定要跑什麼：
#
#   LINT_CMD      要跑的指令。沒設就整支跳過（預設不做事，不會擾民）
#   FAIL_PATTERN  輸出裡出現這個樣式就算失敗。預設抓「N 個 error」
#   PASS_PATTERN  輸出裡出現這個樣式就直接算過，優先於 FAIL_PATTERN
#
# 例（在 ~/.codex/hooks.json 的 Stop 那一段）：
#   LINT_CMD='npm run lint' FAIL_PATTERN='[1-9][0-9]* error' .../lint-gate.sh
#
# 這支不限程式碼。任何「跑得出結果、結果裡看得出成敗」的指令都可以，
# 例如文件連結檢查、拼字檢查、資料完整性腳本。

set -uo pipefail

LINT_CMD="${LINT_CMD:-}"
FAIL_PATTERN="${FAIL_PATTERN:-[1-9][0-9]* (error|ERROR)}"
PASS_PATTERN="${PASS_PATTERN:-}"

input="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  printf '{}\n'
  exit 0
fi

# 已經因為這支被擋過一次了，不要無限迴圈
stop_active="$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)"
if [ "$stop_active" = "true" ]; then
  printf '{}\n'
  exit 0
fi

# 沒設要跑什麼就不做事
if [ -z "$LINT_CMD" ]; then
  printf '{}\n'
  exit 0
fi

# Claude Code 有 CLAUDE_PROJECT_DIR，Codex 沒有，改讀 payload 裡的 cwd
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
    '{decision:"block",reason:("LINT GATE：收工前檢查未通過（" + $cmd + "），請先修完再結束：\n" + $detail)}'
  exit 0
fi

printf '{}\n'
exit 0
