#!/bin/bash
# lint-gate.sh
#
# 這支在 AI 想結束這一輪的時候跑一次你指定的檢查指令。有錯就把錯誤內容丟回去
# 給它，並且不准它結束，直到修完為止。
#
# 為什麼需要：把「記得先跑檢查」寫在規則檔裡是沒有用的。它會忘，而且忘的時候
# 不會講。改成這樣以後，「沒過不准走」是電腦在管，不是靠它自律。
#
# 只有本機的指令在跑，不呼叫任何 AI，不花錢。
#
# 要改的設定有三個，直接改下面，或是在啟動時用同名的環境變數蓋過去：
#
#   LINT_CMD       要跑什麼檢查指令
#   FAIL_PATTERN   檢查結果裡出現什麼文字，就算這次沒過
#   PASS_PATTERN   出現什麼文字算過。留空的話，就是「只要沒出現失敗的文字就算過」
#
# 幾個例子：
#   LINT_CMD='npm run lint'        FAIL_PATTERN='[1-9][0-9]* error'
#   LINT_CMD='ruff check .'        FAIL_PATTERN='^Found [1-9]'
#   LINT_CMD='python3 lint.py'     FAIL_PATTERN='ERROR total: [1-9]'  PASS_PATTERN='ERROR total: 0'

set -uo pipefail

LINT_CMD="${LINT_CMD:-}"
FAIL_PATTERN="${FAIL_PATTERN:-[1-9][0-9]* (error|ERROR)}"
PASS_PATTERN="${PASS_PATTERN:-}"

input=$(cat)

# 這段千萬不要刪。它在問「這次會停下來，是不是因為我上一輪擋了它」。
# 是的話就放行。沒有這段的話，遇到修不好的錯誤，它會變成想結束、被擋、
# 再想結束、又被擋，整個卡死在無限迴圈裡。
if echo "$input" | jq -e '.stop_hook_active == true' >/dev/null 2>&1; then
  exit 0
fi

[ -n "$LINT_CMD" ] || exit 0

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

out=$(eval "$LINT_CMD" 2>&1)

# 檢查指令自己壞掉的時候（打錯字、程式當掉、什麼都沒印出來）一律放行。
# 不能因為檢查工具自己有問題，就讓使用者永遠收不了工。
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
