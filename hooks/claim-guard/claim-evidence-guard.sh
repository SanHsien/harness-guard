#!/bin/bash
# claim-evidence-guard.sh — Stop hook
# 「行動完成宣稱＝事實主張」的強制閘門（task-execution.md 的可執行版）：
#   A) 回覆宣稱「驗證通過/測試通過/實測跑通」→ 本 session 帳本必須有驗證類指令紀錄
#   B) 回覆做出「不存在/找不到」負向斷言 → 帳本必須有搜尋動作紀錄
# 帳本由 claim-ledger-tracker.sh（PostToolUse）寫入。純 bash+jq，無 LLM 呼叫、無額外 token。
# 改寫自 AlethiaQuizForge/no-hallucination（MIT）verify-guard + claim-guard，加中文觸發詞。
# 安全失效模式：欄位缺失或 jq 失敗一律放行（絕不誤擋），只在「有宣稱且零證據」時才擋。

LEDGER_DIR="$HOME/.cache/claude-guard-hooks"

INPUT=$(cat)
SID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null) || exit 0

VERIFY_LEDGER="$LEDGER_DIR/${SID}.verify"
SEARCH_LEDGER="$LEDGER_DIR/${SID}.search"

cleanup() { rm -f "$VERIFY_LEDGER" "$SEARCH_LEDGER"; }

# 第二次通過（已被擋過一輪）：放行並清帳本
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [[ "$STOP_ACTIVE" == "true" ]]; then
    cleanup
    exit 0
fi

LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // empty' 2>/dev/null)
[[ -z "$LAST_MSG" ]] && exit 0

# A) 驗證宣稱（中英）
VERIFY_TRIGGERS='verified|confirmed|all passing|tests? pass|build passes|all green|works now|working now|deployed and verified|驗證通過|測試通過|驗證無誤|實測通過|實測有效|全數通過|建置通過|跑通|已驗證|確認無誤'
if echo "$LAST_MSG" | grep -iqE "$VERIFY_TRIGGERS"; then
    if [[ ! -s "$VERIFY_LEDGER" ]]; then
        cleanup
        cat << 'EOF'
{
  "decision": "block",
  "reason": "CLAIM-EVIDENCE GUARD：你宣稱『驗證通過／測試通過／實測』，但本 session 帳本裡沒有任何驗證類指令紀錄（測試、build、status、diff、實跑）。行動完成宣稱＝事實主張——先實際跑驗證指令，再宣稱結果；若確實無法自動驗證，改寫為『尚未驗證，需人工確認』。"
}
EOF
        exit 0
    fi
fi

# B) 負向存在斷言（中英）
NEG_TRIGGERS="doesn't exist|does not exist|not found|no such|couldn't find|cannot find|can't find|nothing matching|no evidence|there is no|不存在|找不到|沒有找到|查無|沒有任何(相關|紀錄|檔案)|從未出現"
if echo "$LAST_MSG" | grep -iqE "$NEG_TRIGGERS"; then
    if [[ ! -s "$SEARCH_LEDGER" ]]; then
        cleanup
        cat << 'EOF'
{
  "decision": "block",
  "reason": "CLAIM-EVIDENCE GUARD：你斷言某東西『不存在／找不到』，但本 session 帳本裡沒有任何搜尋動作紀錄（Grep/Glob/find/ls）。負向斷言必須先全量搜尋——先搜，再說不存在。"
}
EOF
        exit 0
    fi
fi

cleanup
exit 0
