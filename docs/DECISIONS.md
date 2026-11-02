# 刻意不做的決定

上游審視時決定**不引進**、或引進後**刻意留一部分不做**的項目。每條寫理由與重查條件；
條件成立時再審，不必每次排程重新爭論。逐 commit 的採用紀錄在 [`FORK.md`](../FORK.md)。

## 上游 7b0df03 → adc8928（2026-10-25 審視）

| 項目 | 來源 | 不做的理由 | 重查條件 |
|---|---|---|---|
| `write-manifest` hook，以及依賴它的 checkpoint lite mode、`stage-own-edits.sh`、`todo_closeouts`、提交鎖 | 7b0df03、e9a4734 | 上游只有 bash 版（Claude Code + Codex）。本 fork 的承諾是四個 agent、Windows 優先：要另寫 Python 版、接進 installer／verifier／CI，checkpoint 的改動也要一起搬。逐段挑會留下指向不存在腳本的文字。 | 維護者決定採用 write-manifest（並補 Windows 版）時，整組一起搬，跑 FORK.md 列的測試。 |
| neat-freak 併入 checkpoint（`/checkpoint full` 取代 `/neat-freak`） | adc8928 | 建立在上一列的 checkpoint 新版之上；本 fork 的 checkpoint 仍是舊版，且 README、安裝器列舉的是兩個獨立 skill。 | 與上一列同時處理。 |
| `block-outgoing-comms` hook | e9a4734 | 新 guardrail，上游只有 bash 版，Claude 端只是 ask、Codex 端 fail closed；本 fork 要 Python 版才能涵蓋 Windows／Cursor／Antigravity，且要決定和 `danger-zone-guard` 的憑證外洩規則怎麼分工。這是產品取捨，不是缺陷修正。 | 維護者要攔 MCP 對外發送（send／reply／publish 類工具）時。 |
| `humanizer` skill | e9a4734 | 寫作風格 skill，不在 guardrail kit 的定位內；另帶三份第三方 MIT attribution。 | 維護者要求加入寫作類 skill 時。 |
| plugin marketplace（`.claude-plugin/marketplace.json`） | e9a4734、7474dfd | 只服務 Claude Code；本 fork 的安裝契約是 `install.py` 合併、備份、讀回驗證、四個 agent 與 Windows 絕對路徑，marketplace 給不了這些保證。 | Claude Code plugin 的 hook 能在原生 Windows 用 Python 版與絕對路徑運作，且維護者想提供第二種安裝方式時。 |
| 退役 review-loop、info-diet、phantom-pushback、asd-ste100、iso-24495、claude-md-template | e9a4734、365f5c3 | 上游為了精簡而退役，不是因為它們壞了；本 fork 的 README、安裝器、CI compile 都還在用。 | 維護者決定精簡 skill 清單時；上游保存在 tag `retired-archive-2026-10-22`。 |
| claim-guard 的 subagent 帳本（`agent_id` 分帳 + `SubagentStop`） | e9a4734 | 改了語意：tracker 以 `agent_id` 分帳後，主 session 委派 subagent 跑測試再宣稱「通過」會被擋；`SubagentStop` 在 Codex、Cursor、Antigravity 沒有對應事件，只能做一半。同一 commit 的「過期驗證」與「引號內提及」已移植。 | 實際觀察到 subagent 無證據宣稱完成而主 session 照單全收時。 |
| README、CLAUDE.md、AGENTS.md、hooks/README.md 的改寫 | e9a4734、7474dfd、365f5c3、adc8928 | 對應上游的新版面（plugin、退役 skill）；本 fork 的文件結構不同（中文主檔、`AGENTS.md` 唯一指令檔）。 | 上游改寫涉及 hook 行為或風險邊界的說法時，才逐段併入。 |

## 上游自身的瑕疵（未回貢）

- `skills/explain/SKILL.md`：上游 e9a4734 把第 4 點改成「不要問要不要繼續、一次講完」，但同檔
  document mode 的範例 prompt 仍寫「a closing offer to go deeper if they want it」。本 fork 原樣同步，
  保持與上游一致；要回貢或本地修正由維護者決定（FORK.md：上游的 bug 送回去，需要當次明確同意）。

## 上游 adc8928 → b47f3e9（2026-11-02 審視）

來源：[b47f3e9](https://github.com/agentcrew-academy/harness-starter-kit/commit/b47f3e91b5468cf84a14a92c84d0b344ec276027)。
完整差異僅涉及新版 checkpoint 與其宣傳，沒有既有五個核心 hook 的修正。逐項決策如下；
不將「完成審查」視為「決定採用 write-manifest」。

| 項目／檔案 | 結論與理由 | 重查條件 |
| --- | --- | --- |
| `skills/checkpoint/SKILL.md`、`references/lite.md`：自動 lite（無事實清單且至多 5 個歸屬檔）、前景低成本 worker 與新版 manifest 欄位 | **暫緩**。本 fork 尚未引進依賴 write-manifest 的 checkpoint lite；直接換文字會指向不存在的腳本與欄位。模型選擇也應遵守使用端自己的路由規則。 | 維護者決定採用 write-manifest 與新版 checkpoint 時整組處理，驗證四個 agent 的歸屬與路由。 |
| `references/closure-protocol.md`：開場快照、混合作者 hold list、todo 日期、鎖內重查、全部 repo 完成後才清 manifest | **暫緩**。歸屬表、Edit 重播與清理順序依賴本 fork 沒有的 write-manifest／edit-log；不能只移植規則就宣稱能安全分帳。日誌與 todo 的加強也隨整套協定一起處理。另外，上游新範例把 `git commit` 接在 `;` 之後，暫存失敗時照樣提交，這是不逐字照抄的又一個理由。 | 同上，另測多 repo、共享檔案、缺少快照與保留未提交內容。 |
| `scripts/stage-own-edits.sh`：helper／git 失敗統一回 exit 5 | **暫緩**。本 fork 沒有此腳本；是未引進功能的錯誤處理，不是本 fork 現存缺陷。 | 引進該腳本時一起採用，補 helper 失敗、git add／update-index 失敗的回歸測試與 Windows Python 版。 |
| `scripts/bash-writes.py`：從 transcript 找 shell／subagent 寫入候選 | **暫緩**。只讀 Claude Code transcript，shell 目標為啟發式候選，不能證明唯一作者；不涵蓋其他三個 agent 的 transcript 與 PowerShell 寫入。 | 採用新版 checkpoint 時，明訂各 agent 的來源與降級方式，測試 Windows 路徑、PowerShell、誤報與漏報。 |
| `references/lessons.md`：重複糾正記錄、Seen 門檻、提案核准與可選月檢 | **不採用本次自動觸發**。收工自動寫 memory／重複錯誤紀錄會擴大本 fork 的收工副作用與成本；記憶及全域規則的修改應由使用者明確授權，不因糾正次數自動寫入。 | 維護者明確要求 lessons 功能，且先定義唯讀預設、寫入授權、資料保存與額度界線。 |
| `references/sync-matrix.md`、`references/sync-protocol.md`：跨檔狀態對帳、實查 todo／memory；`scripts/enumerate.sh`：註解用詞整理 | **暫緩**。屬已暫緩的 neat-freak 併入 checkpoint 協定；本 fork 仍以獨立 neat-freak 運作。沒有需單獨搬入的執行邏輯修正。 | 新版 checkpoint／neat-freak 整組採用時，核對同步矩陣與實查證據。 |
| `.claude-plugin/marketplace.json`、`README.md`、`README.zh-TW.md`：上述新版 checkpoint 宣傳 | **不採用**。本 fork 沒採用 marketplace 或此新版流程，不能在雙語 README 宣稱具備這些能力。 | 對應功能實作與四個 agent 驗收完成，且維護者決定提供 marketplace 安裝時。 |

PR／issue 2026-11-02 沒有新項目（`--state all` 實查仍僅 PR #2、issue #1），既有決策不變。
