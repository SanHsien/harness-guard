# CLAUDE.md

給 Claude Code 在這個 repo 工作時的指引。**安裝流程、對話原則、驗證要求的唯一真相源是
[`AGENTS.md`](AGENTS.md)**——先讀它。本檔只補 Claude Code 專屬的路徑與介面細節，不重複規則。

## 路徑

| 東西 | 位置 |
|---|---|
| hook 腳本 | `~/.claude/hooks/`（平放，不保留 repo 的資料夾層次） |
| hook 註冊 | `~/.claude/settings.json` 的 `hooks` 區塊 |
| skills | `~/.claude/skills/`，各自保留自己的資料夾，不需註冊 |
| 規則檔 | `~/.claude/CLAUDE.md`；可選規則檔放 `~/.claude/rules/` |
| 設定範本 | macOS/Linux 用 `settings-example.json`；**Windows 用 `settings-example.windows.json`** |

Windows 的 `~` 在不同 shell 下展開結果不同，設定檔裡一律寫完整絕對路徑
（`C:\Users\<你>\.claude\hooks\...`）。原因見 [`docs/windows-install.md`](docs/windows-install.md)。

## 這個 repo 用到的 hook 事件

- `PreToolUse` + matcher `Write|Edit|MultiEdit` → no-emoji-guard
- `PreToolUse` + matcher `Bash` → test-gate-guard
- `PostToolUse` + matcher `Bash|Grep|Glob` → claim-ledger-tracker
- `Stop` → claim-evidence-guard、lint-gate

放行是安靜結束（exit 0），攔截是 `exit 2` + 訊息寫 stderr；claim-evidence-guard 例外，
它印 `{"decision":"block","reason":"..."}`。專案目錄從環境變數 `CLAUDE_PROJECT_DIR` 讀。

## 改完設定必做

1. 備份 `settings.json`，改完驗證 JSON 仍合法（UTF-8 讀取，不要用系統預設編碼）。
2. 告訴使用者要**完全關掉 Claude Code 再開**，hook 只在啟動時載入。
3. 跑 `python scripts/verify-install.py`，exit code 0 才算裝好。沒跑過就不要說裝好了。
