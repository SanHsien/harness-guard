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
