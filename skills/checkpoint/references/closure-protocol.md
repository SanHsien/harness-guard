# Checkpoint Closure Protocol

輸入是主線產生的 closure manifest。你是唯一 closure worker；不得再派 subagent，也不得重新摘要整段對話。

## 1. 重驗狀態

1. 用 `date` 核實 manifest 日期與時區。
2. 逐 repo 重跑 status／branch；同一路徑的 vault 不重複處理。
3. manifest 未列出的 dirty files 視為並行或他人修改；先讀 diff 判斷歸因，無法安全分離就保留並警告。
4. 檢查 coverage：每個 changed file 與列出的外部／排程／付款／待辦動作都必須分類。發現缺口就停止並退回主線補 manifest，不自行猜測。

## 2. Daily 只寫一次

除 `git-only`、`daily_action: skip_duplicate` 或沒有 material session 外，讀取：

`<obsidian-skill-dir>/references/daily-log-protocol.md`

依 manifest 的 `daily_entries` 寫一次。不要 invoke 完整 Obsidian skill；不要在 neat-freak 階段再寫。

## 3. 條件式事實對帳

- `git-only`：跳過。
- `scoped` 且 fact list 為空：跳過，回報 `sync: skipped (no fact delta)`。
- 其餘：完整讀取 `<neat-freak-skill-dir>/references/sync-protocol.md`，傳入 manifest 的 mode、memory_mode、fact list 與路徑。

sync protocol 只做對帳，不會 commit；完成後再進下一節。

## 4. 驗證、stage、commit、push

對每個 repo：

1. 讀 status 與 diff，確認可歸因檔案；排除 `.env`、`credentials*`、`*.secret`、session dumps、lock files 與 manifest 未授權的敏感資料。
2. 跑與變更風險相稱的 tests；至少 `git diff --check`。若該 repo 有自己的 lint／檢查腳本，一併跑過；修復範圍只限本次收尾相關的項目，不擴張成整套定期維護。
3. 逐檔 stage，禁止盲目 `git add -A`。掃 staged diff 的 secret-like pattern，但不要把命中值印出。
4. staged diff 為空就回報 clean，不製造空 commit。
5. Conventional Commit subject ≤72 字元；只有系統或使用者明確要求才加 `Co-Authored-By`。
6. push 當前 branch；失敗照實回報，不 force push。
7. 驗證 local `HEAD == origin/<branch>`。若需要 live remote 證據且網路可用，再比對 `git ls-remote`。

Vault 與當前 repo 不同時，各自 commit；只收本 session 可歸因檔案。重疊且不可分離時停止該 repo，不把未知變更 sweep 進去。

## 5. 回傳

```text
daily: written | skipped (<reason>)
sync: skipped | scoped | full (<gate summary>)
repos:
- <path> <hash|clean> pushed=<branch|no>
preserved:
- <unrelated dirty file>
warnings:
- <item>
```

附 enumerate 最終證據一次；不要重貼完整 diff 或協議。
