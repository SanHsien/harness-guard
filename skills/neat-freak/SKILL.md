---
name: neat-freak
description: "Deep fact reconciliation for KB masters, project docs, and authorized memory. Use for /neat-freak, 完整對帳, 知識同步, 文檔同步, 記憶清理. With checkpoint, enable full mode instead of a second run."
---

# 潔癖 — 事實對帳引擎

本 skill 對帳「事實」：客戶狀態、合約版本、排期、款項、待辦與開發文件。它不負責寫 daily，也不負責 git commit / push。

## 與 checkpoint 組合時

若同一使用者指令同時包含 `checkpoint`：

1. 不另建 plan、不另做 Fact Detection、不另派 subagent。
2. 告知 checkpoint manifest 使用 `mode: full`、`memory_mode: update`。
3. 由 checkpoint 的唯一 closure worker 讀本 skill 的 `references/sync-protocol.md`。

這樣 daily、對帳、stage、push、驗收各只發生一次。

## 單獨執行時

### 1. Fact Detection

主線回顧本次對話一次，產出 `fact_list`（事實 → 波及檔案），並解析 active skill dir、memory dir、vault、project roots。映射不確定才讀 `references/sync-matrix.md`。

即使 fact list 為空，明確點名 neat-freak 仍代表 `mode: full`；但要靠 enumerate 結果與最近相關檔案做 progressive disclosure，不全量載入 vault 或 rollout summaries。

### 2. 一次 fresh-context 執行

用一個不承接主線長對話的 bounded subagent；Codex 明確設 `fork_turns: "none"`，Claude Code 使用 `model: sonnet` 的 fresh general-purpose Agent/Task。prompt 只帶：

- `mode: full`
- `memory_mode: update`
- 完整 fact list
- active neat-freak skill dir、memory dir、vault、project roots

第一句要求完整讀取 `references/sync-protocol.md` 並照做。不得寫 daily、commit 或 push。沒有可用 subagent 時主線自己執行。

### 3. 驗收

主線抽讀 1–2 個宣稱修改過的檔案，確認 enumerate 最終輸出與 GATE 結果，補掉能安全處理的失敗，最後只回報同步證據、變更與未處理項目。

## 邊界

- `/obsidian log`：流水帳。
- `/checkpoint`：唯一完整收尾入口。
- `vault-maintenance`：週期性 lint、歸檔、索引與鏡像維護。

沒有 enumerate 最終輸出，就沒有完成 neat-freak。
