#!/bin/bash
# claim-ledger-tracker.sh — PostToolUse (Bash|Grep|Glob)
# 默默記錄本 session 的「驗證類指令」與「搜尋類動作」到帳本，
# 供 claim-evidence-guard.sh 在 Stop 時比對宣稱與證據。
# 改寫自 AlethiaQuizForge/no-hallucination（MIT）的 verify-tracker + search-tracker，
# 合併為單一腳本並改用 session 隔離帳本（避免污染 repo 工作樹）。

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
