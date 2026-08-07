#!/bin/bash
# lint-gate.sh — Stop hook
#
# 收工閘門：Claude 想結束這一輪時，先跑你指定的檢查指令；有錯就把錯誤丟回去
# 要它修完再結束。純本地腳本，不呼叫任何模型，不花 token。
#
# 為什麼要有這個：把「記得跑 lint」寫進 CLAUDE.md 是沒有強制力的，模型會忘、
# 會覺得這次不重要。做成 Stop hook 之後，「沒過就不准收工」變成系統行為，
# 不再依賴模型自律。
#
# 設定：改下面三個變數，或用同名環境變數覆寫。
#   LINT_CMD       要跑的檢查指令（相對路徑以 CLAUDE_PROJECT_DIR 為基準）
#   FAIL_PATTERN   在輸出中命中這個 regex 就算失敗
#   PASS_PATTERN   命中這個就算通過；留空表示「只要沒命中 FAIL_PATTERN 就算過」
#
# 例：
#   LINT_CMD='npm run lint'        FAIL_PATTERN='[1-9][0-9]* error'
#   LINT_CMD='ruff check .'        FAIL_PATTERN='^Found [1-9]'
#   LINT_CMD='python3 lint.py'     FAIL_PATTERN='ERROR total: [1-9]'  PASS_PATTERN='ERROR total: 0'

set -uo pipefail

LINT_CMD="${LINT_CMD:-}"
FAIL_PATTERN="${FAIL_PATTERN:-[1-9][0-9]* (error|ERROR)}"
PASS_PATTERN="${PASS_PATTERN:-}"

input=$(cat)

# 防無限迴圈：這一輪已經是被本 hook 擋下來才停的，就放行。
# 沒有這段的話，修不好的錯誤會讓 Claude 永遠結束不了。
if echo "$input" | jq -e '.stop_hook_active == true' >/dev/null 2>&1; then
  exit 0
fi

[ -n "$LINT_CMD" ] || exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

out=$(eval "$LINT_CMD" 2>&1)

# Fail-open：檢查指令自己壞掉（找不到、crash、沒有輸出）時放行，
# 不要因為工具壞了就讓使用者永遠收不了工。
[ -n "$out" ] || exit 0

if [ -n "$PASS_PATTERN" ]; then
  echo "$out" | grep -qE "$PASS_PATTERN" && exit 0
fi

if echo "$out" | grep -qE "$FAIL_PATTERN"; then
  {
    echo "收工前檢查未通過（${LINT_CMD}），請先修完再結束："
    echo "$out" | grep -E "$FAIL_PATTERN" | head -20
  } >&2
  exit 2
fi

exit 0
