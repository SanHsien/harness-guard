#!/bin/bash
# claim-evidence-guard.sh
#
# 這支在 AI 想要結束這一輪對話的時候跑，負責對帳。
#
# 它檢查兩件事：
#   一、它說了「測試過了」「驗證通過」「實測沒問題」→ 帳本裡就要有真的跑過檢查的紀錄
#   二、它說了「找不到」「沒有這個東西」→ 帳本裡就要有真的搜尋過的紀錄
# 對不上就擋下來，不准結束，並且把缺什麼講給它聽。
#
# 帳本是隔壁的 claim-ledger-tracker.sh 記的，兩支要一起裝，少一支就失效。
#
# 為什麼需要這個：「我測試過了」這句話對 AI 來說幾乎沒有成本，它可以在完全沒跑過
# 的情況下用一模一樣的語氣講出來，你分辨不出來。與其相信它，不如去查紀錄。
#
# 全程只有本機的小指令在跑，不呼叫任何 AI，不花錢。
#
# 讀不到資料或格式不對的時候一律放行，寧可漏擋也不誤擋。只有在「明確講了、
# 而且完全零紀錄」的情況下才會攔。
#
# 改寫自 AlethiaQuizForge/no-hallucination（MIT 授權）的 verify-guard 與 claim-guard，
# 合併並加上中文的觸發詞。

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
