---
name: checkpoint
description: "Close a session once: daily log, optional fact sync, selective commit/push, and remote verification. Use for /checkpoint, 收尾, 存檔, 推上去, commit and push, or checkpoint + neat-freak."
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Agent Read
---

# Checkpoint — 單一收尾入口

`checkpoint` 是公開收尾入口；`neat-freak` 是它可選用的事實對帳引擎。兩者同時被點名時，只跑一條 closure 流程，不得各自摘要、派工、寫 daily 或驗收一次。

## 模式

- `scoped`（預設）：寫一次 daily；有 fact list 才做針對性對帳，之後 commit + push。
- `full`：使用者同時點名 `neat-freak`、知識同步、記憶清理或完整收尾；做完整 GATE 對帳後再 commit + push。
- `git-only`：只有使用者明確說不寫日誌／不同步時使用。

## 1. 主線只建立一次 closure manifest

先用當前平台的 task/plan 機制建立一份收尾計畫；不要為 neat-freak 再建第二份。

1. 用 `date` 取得日期與時區。
2. 檢查當前 repo（以及 manifest 列出的其他 project roots）的 `git status --porcelain`、`git diff --stat HEAD`、目前 branch。
3. 回顧本次對話一次，同時產出：
   - `session_summary`：完成事項／決定／踩坑，各 0–3 條。
   - `fact_list`：改變的事實 → 波及檔案；不是單純 touched files。
   - `daily_entries`：要寫入 daily 的精簡內容。
   - `repos`：repo、branch、可歸因檔案、已跑測試。
   - `coverage`：每個 changed file，以及每個對外動作／排程／付款／待辦變更，都標成 `fact_delta: yes`（連到 fact list）或 `fact_delta: no`（附一句理由）。有未分類項目不得派工。
4. 比對今日 daily、recent commits 與目前檔案狀態；其他 session 已寫入更晚且相同的內容時標 `daily_action: skip_duplicate`，不得重複或倒填。
5. manifest 必含 `mode`、`memory_mode`、目前用到的各個流程腳本所在資料夾、記憶資料夾、知識庫根目錄、以及所有要收尾的專案資料夾。

`memory_mode` 預設 `read-only`；只有使用者明確要求 `neat-freak`、記憶同步或記憶清理時才是 `update`。

## 2. 只執行一次

把 manifest 交給一個 fresh-context、一般用途的 bounded subagent：

- Codex：使用 `fork_turns: "none"`，prompt 只帶 manifest 與本檔路徑。
- Claude Code：使用 `model: sonnet` 的 fresh general-purpose Agent/Task subagent；它不會看到主線對話歷史，但仍會載入適用的 CLAUDE.md／權限。delegation prompt 只帶 manifest 與本檔路徑。

第一句要求它完整讀取 `references/closure-protocol.md`，不得再派 subagent，也不得另行 invoke neat-freak。若平台沒有 subagent，或任務只是單 repo 的 `git-only`，主線直接照該協議做。

## 3. 主線驗收

subagent 回報是主張，不是事實：

1. 若有同步修改，抽讀 1–2 個宣稱修改過的檔案。
2. 確認 daily 同一事項只出現一次。
3. 逐 repo 檢查回報 hash、`git log -1 --oneline` 與 `HEAD == origin/<current-branch>`。
4. 重看 `git status --short`：本次可歸因修改應已收尾；無關或並行修改應原樣保留並列出。

## 精簡回報

```text
daily: written | skipped (<reason>)
sync: skipped | scoped | full (<GATE result>)
commit: <repo> <hash> | clean
vault: <hash> | clean | preserved unrelated changes
pushed: <branches>
warnings: none | <items>
```

不 force push；不盲目 `git add -A`；不因「想要 clean」而收進無法歸因的修改。
