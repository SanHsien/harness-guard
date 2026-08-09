# 三支攔截工具：兩個版本

每一支底下都有兩個資料夾：

```
hooks/<工具名>/
├── claude-code/   給 Claude Code 用
└── codex/         給 Codex 用
```

**判斷邏輯兩邊一模一樣。**擋什麼、放什麼、怎麼算證據，是同一套。不一樣的只有跟平台介面有關的那幾行。

裝哪一個看你用哪個工具。兩個都用就兩個都裝，帳本目錄是分開的（`~/.cache/claude-guard-hooks` 與 `~/.cache/codex-guard-hooks`），不會互相干擾。

## 設定檔怎麼寫

- Claude Code → 併進 `~/.claude/settings.json`，範例在 repo 根目錄的 `settings-example.json`
- Codex → 併進 `~/.codex/hooks.json`，範例在 `codex-hooks-example.json`，另外 `~/.codex/config.toml` 要有 `hooks = true`

## 兩邊到底差在哪

事件名稱是**一樣的**（`PreToolUse`、`PostToolUse`、`Stop`、`SessionStart`、`UserPromptSubmit` 這些），`matcher` ＋ `hooks` 的結構也一樣。真正的差異是下面五點，移植其他 hook 時照這張表改就對了。

| | Claude Code | Codex |
|---|---|---|
| 設定放哪 | `settings.json` 的 `hooks` 區塊 | 獨立的 `~/.codex/hooks.json`，另外 `config.toml` 要 `hooks = true` |
| 這一輪的識別碼 | `session_id` | **`turn_id`**（寫成 `.turn_id // .session_id` 兩個都試最保險） |
| matcher 的工具名 | `Write`／`Edit`／`MultiEdit`／`Bash`／`WebFetch` | 改檔案是 `apply_patch`，執行指令是 `exec`／`shell`／`exec_command`，抓網頁是 `web_fetch` |
| 專案目錄 | 環境變數 `CLAUDE_PROJECT_DIR` | 沒有這個。改讀 payload 裡的 `cwd` |
| 放行時要輸出什麼 | 安靜結束就好 | **要印一個 `{}`**，什麼都不印會被當成異常 |
| 擋下來怎麼表達 | `exit 2` ＋ 訊息寫到 stderr | 印 `{"decision":"block","reason":"..."}` |
| 信任機制 | 無 | hook 要先被信任才會跑，第一次啟用要確認 |

另外 Codex 有 `PostCompact`，Claude Code 有 `PreCompact`、`SessionEnd`、`Notification`。兩邊各有對方沒有的事件，掛之前先確認你要的那個存不存在。

`stop_hook_active`、`last_assistant_message`、`tool_name`、`tool_input` 這幾個欄位兩邊同名，可以直接沿用。

## 想自己移植別的 hook

上面那張表就是全部。核心邏輯不用動——`claim-ledger-tracker` 兩個版本不含註解各是 26 行與 32 行，多出來的六行全是「沒有 jq 就跳過」這類防禦，判斷用的那串比對式一個字都沒改。

移植完**一定要實際觸發一次確認它真的有反應**。不要看它沒報錯就當成生效了——那正是這三支想防的事。
