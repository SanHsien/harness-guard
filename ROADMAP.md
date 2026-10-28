# 路線圖

> 本 repo 後續工作的單一真相源。做完一項，就在同一個 commit 刪掉那一列；新工作只加在這裡。
> 現況段的數字是 2026-10-29 依 `main` `2cb07a94d890` 查的快照，開工前先重查 GitHub。

## 現況
`agentcrew-academy/harness-starter-kit` 的衍生版，負責在 agent 動手前後與收工時實際攔截（危險指令、無證據完成宣稱、紅燈仍提交等），含跨 Claude Code／Codex／Cursor／Antigravity 的安裝器與 live-fire 驗證器（`AGENTS.md:10-18`）。2026-10-29 查：open PR 0、issue 已停用（未查到 issue 數）、Dependabot 與 code scanning open 0；`main` 已前進到 `2cb07a94d890`（2026-10-29 早些時候的快照是 `45165fab75b1`，之後多 2 個 commit，`gh api repos/SanHsien/harness-guard/compare/45165fab75b1...2cb07a94d890`），該 SHA 的 CI、CodeQL 皆 success（`gh run list -R SanHsien/harness-guard --branch main`）；Upstream check 最近一次（10-26 排程）success，上游 `main` 仍是已審的 `adc8928`。repo 健康，卡點是修正還沒裝回維護者自己的機器：repo 內沒有 10-26～10-28 修正已重裝到使用者全域 hooks 的紀錄。

## 近期：可以直接動手
| 項目 | 為什麼 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 把 `main` 最新版重裝到維護者使用中的四個 agent，並跑 live-fire 驗證 | 10-26～10-28 修了 test-gate-guard、danger-zone-guard、claim-guard、no-emoji-guard 與安裝器備份；repo 綠不代表使用者那份 hook 已是新版 | `python scripts/install.py --dry-run --agent all --hooks all --skills all` 檢視後實裝；`python scripts/verify-install.py --agent all` 全部 PASS；已安裝檔與 `main` 對應檔雜湊相同 | 維護者 | `gh api repos/SanHsien/harness-guard/compare/45165fab75b1...2cb07a94d890`（改了 `hooks/claim-guard/*`、`hooks/no-emoji-guard/codex/no-emoji-guard.py`、`scripts/install.py`）；`CHANGELOG.md` 2026-10-26 段 |
| 決定 `skills/explain/SKILL.md` 上游原有矛盾的處理：回貢上游，或本地修正 | 上游 e9a4734 改了第 4 點「一次講完」，同檔 document mode 範例仍要求結尾提議深入；回貢需維護者當次明確同意 | 擇一：上游 PR 連結記進 `FORK.md`；或本地修正並在 `docs/DECISIONS.md` 註明偏離上游；`python -m unittest discover -s tests -p "test_*.py"` 綠 | 維護者 | `docs/DECISIONS.md:19-23` |
| CHANGELOG「水位必須是非負整數」補上「或 null（表示缺省）」，中英兩份同步 | 程式接受 null，文件說法比行為窄（`scripts/check_upstream_updates.py:60` 接受 `None`） | `CHANGELOG.md` 與 `CHANGELOG.en.md` 該句一致且與 `scripts/check_upstream_updates.py` 的驗證行為相符 | Claude Haiku | `CHANGELOG.md:39`；`scripts/check_upstream_updates.py:60` |

## 中期：等條件成立再做
| 項目 | 觸發條件 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 審上游新 commit／PR／issue，逐項採用或寫進不做清單 | `Upstream check` 轉 failure（上游 `main` 超過 `scripts/upstream_baseline.json` 的 `reviewed_through`，或 PR／issue 編號超過水位） | `FORK.md` 或 `docs/DECISIONS.md` 逐項寫結論；baseline 推進；`python scripts/check_upstream_updates.py` exit 0 | Codex | `scripts/upstream_baseline.json`；`docs/DECISIONS.md:6-17` |
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
