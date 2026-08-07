#!/bin/bash
# claim-ledger-tracker.sh
#
# 這支像行車紀錄器：AI 每跑一個指令它就在旁邊記一筆，全程不出聲、不干擾。
#
# 它只記兩類事：
#   一、跑過哪些檢查類的指令（測試、編譯、版本查詢那些）
#   二、做過哪些搜尋（找檔案、找關鍵字）
#
# 記下來的東西給隔壁的 claim-evidence-guard.sh 用，那支會在收工時拿這本帳
# 去對「它剛才說的話有沒有憑據」。兩支要一起裝。
#
# 帳本放在使用者家目錄的快取資料夾，按對話分開存，不會弄髒你的專案。
#
# 改寫自 AlethiaQuizForge/no-hallucination（MIT 授權）的 verify-tracker 與
# search-tracker，合併成一支並改用隔離的帳本路徑。

LEDGER_DIR="$HOME/.cache/claude-guard-hooks"

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
SID=$(echo "$INPUT" | jq -r '.session_id // "default"')

VERIFY_LEDGER="$LEDGER_DIR/${SID}.verify"
SEARCH_LEDGER="$LEDGER_DIR/${SID}.search"

case "$TOOL" in
    Grep|Glob)
        mkdir -p "$LEDGER_DIR"
        echo "$(date +%H:%M:%S) $TOOL" >> "$SEARCH_LEDGER"
        ;;
    Bash)
        CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
        [[ -z "$CMD" ]] && exit 0
        # 驗證類：測試、建置、狀態、健康檢查、diff、lint、實測腳本
        if echo "$CMD" | grep -qE '(--version|npm (run build|test)|pytest|jest|cargo test|go test|make test|uv run|vault-lint|visual-drift-lint|py_compile|bash -n|jq (-e |\.)|curl.*-[sI]|git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(status|diff|log)|systemctl (status|is-active)|test -[fedrwx]|grep -[qcl]|wc -[lcw]|python3 (-c|-m)|node -e|pdfinfo|cmp -s|diff -r)'; then
            mkdir -p "$LEDGER_DIR"
            echo "$(date +%H:%M:%S) ${CMD:0:120}" >> "$VERIFY_LEDGER"
        fi
        # 搜尋類：grep/rg/find/ls/gh api 查詢
        if echo "$CMD" | grep -qE '(^|[|;&][[:space:]]*)(grep|rg|find|ls|fd|gh api|mdfind)[[:space:]]'; then
            mkdir -p "$LEDGER_DIR"
            echo "$(date +%H:%M:%S) ${CMD:0:120}" >> "$SEARCH_LEDGER"
        fi
        ;;
    *) exit 0 ;;
esac

exit 0
