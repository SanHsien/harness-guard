# 路線圖

> 本 repo 後續工作的單一真相源。做完一項，就在同一個 commit 刪掉那一列；新工作只加在這裡。
> 現況段於 2026-11-08 依 `main` `54de47c2a4b4` 與 GitHub 唯讀查詢更新；2026-11-02 審完上游 `b47f3e9`（12 檔）的結果另見 `FORK.md`。

## 現況
`agentcrew-academy/harness-starter-kit` 的衍生版，提供跨 Claude Code／Codex／Cursor／Antigravity 的 guardrail hooks、安裝器與 live-fire 驗證器（`AGENTS.md:10-18`）。2026-11-08 實查：open PR 0、issue 已停用、Dependabot 與 code scanning open 0（`gh api` 回傳筆數 0）；`main` 為 `54de47c2a4b4`，該 SHA 的 CI（2026-11-02）與 CodeQL（2026-11-03）success，Upstream check 最近一次（`3ed7016b252b`）success。2026-11-02 審完上游 `b47f3e9`，baseline 已推進到該 commit，暫緩／不採用的理由見 `FORK.md` 與 `docs/DECISIONS.md`；PR／issue 水位維持 #2／#1。2026-11-08 `python scripts/verify-install.py --agent all` 在維護者機器回報 `86 checked, 4 failed`（已安裝的 hook 仍是舊版），所以重裝項目保留。`skills/explain` 上游矛盾已本地修正，決定見 `docs/DECISIONS.md` 〈上游自身的瑕疵（本地修正，未回貢）〉。

## 近期：可以直接動手
| 項目 | 為什麼 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 把 `main` 最新版重裝到維護者使用中的四個 agent，並跑 live-fire 驗證 | 2026-11-08 `verify-install.py --agent all` 4 項 FAIL：claim-ledger-tracker 與 Codex tracker matcher 缺 Edit／Write／apply_patch、Antigravity claim-guard matcher 缺 `grep_search`／`replace_file_content`／`run_command`／`write_to_file`、lint-gate 專案開關測試；Codex 的 no-emoji-guard 另顯示 `"enabled": false`（既有停用設定，不屬失敗）。repo 綠不代表使用者那份 hook 已是新版；實裝會改全域 agent 設定，需在授權下由能改全域設定的 session 執行 | 先 `python scripts/install.py --dry-run --agent all --hooks all --skills all` 檢視（2026-11-08 dry-run exit 0，會替換七支 Codex hook 並補登記一筆 claim tracker）；實裝後 `python scripts/verify-install.py --agent all` 全部 PASS（exit 0）；已安裝檔與 `main` 對應檔雜湊相同；已存在的 skills 預設不覆蓋，需 `--force` 才會更新 | 艦隊規劃長（全域設定授權下） | `python scripts/verify-install.py --agent all`（2026-11-08，exit 1，86 checked／4 failed）；`CHANGELOG.md` 2026-10-26～10-28 段 |

## 中期：等條件成立再做
| 項目 | 觸發條件 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 審上游新 commit／PR／issue，逐項採用或寫進不做清單 | `Upstream check` 轉 failure（上游 `main` 超過 `scripts/upstream_baseline.json` 的 `reviewed_through`，或 PR／issue 編號超過水位） | `FORK.md` 或 `docs/DECISIONS.md` 逐項寫結論；baseline 推進；`python scripts/check_upstream_updates.py` exit 0 | Codex | `scripts/upstream_baseline.json`；最新決策 `docs/DECISIONS.md` 〈上游 adc8928 → b47f3e9（2026-11-02 審視）〉 |
| 引進 `write-manifest` hook 與相依的新版 checkpoint（含 neat-freak 併入），補 Python 版 | 維護者決定採用；整組一起搬，不逐段挑 | 四個 agent 的 Python 版接進 `install.py`、`verify-install.py` 與 CI；`FORK.md` 列的測試全綠 | Claude Opus | `docs/DECISIONS.md:10-11` |
| 新增 `block-outgoing-comms` guardrail（Python 版），並劃清與 `danger-zone-guard` 憑證規則的分工 | 維護者要攔 MCP 對外發送（send／reply／publish 類工具） | 新 hook 有四個 agent 的安裝與 live-fire 驗證；與 danger-zone-guard 不重複攔同一事件的測試 | Claude Opus | `docs/DECISIONS.md:12` |
| claim-guard 改以 subagent 分帳（`agent_id`＋`SubagentStop`） | 實際觀察到 subagent 無證據宣稱完成、主 session 照單全收 | 有重現該情境的測試；主 session 委派測試後宣稱通過不被誤擋；不支援 `SubagentStop` 的 agent 在文件註明只做一半 | Claude Opus | `docs/DECISIONS.md:16` |

## 刻意不做
| 不做什麼 | 理由 | 什麼情況下重新考慮 |
| --- | --- | --- |
| 攔 `pytest \| tee log && git commit`、`bash -c "..."`、`$(echo main)` 這類管線或刻意繞過 | hook 是減速帶不是沙箱，退出碼來自 `tee` 屬設計限制；硬攔會大量誤攔 | 實際觀察到 agent 以這些寫法繞過並造成紅燈提交 |
| 在 hook 內加覆蓋率、突變測試、複雜度等量化門檻 | 量化門檻歸 ai-quality-gates；本 repo 只做「動作當下攔不攔」，`lint-gate` 只跑專案自己宣告的 lint | ai-quality-gates 提供可由 hook 呼叫的單一指令且維護者要求在收工時強制 |
| 檢查路由宣告（`solo`／`delegate`／`audit`／`full`）或決定派工對象 | 歸 agent-advisor 的 `route-guard` 與路由規則 | 不重新考慮 |
| 引進上游的 plugin marketplace、`humanizer` skill，或跟著上游退役 review-loop 等 skill | 安裝契約是 `install.py` 合併、備份、讀回驗證；寫作類 skill 不在定位內；退役 skill 本 fork 仍在用（`docs/DECISIONS.md:13-15`） | 依 `docs/DECISIONS.md` 各列的重查條件 |

## 維護方式
上游以 commit 加 PR／issue 水位追蹤，`Upstream check` 每週跑，判斷寫 `FORK.md` 與 `docs/DECISIONS.md`。修上游的 bug 才回貢，且要維護者當次同意。每次改 hook 都要中英 CHANGELOG 同步、CI（Ubuntu／Windows × Python 3.11／3.14 四組）綠，並提醒維護者重裝。
