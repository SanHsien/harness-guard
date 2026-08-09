# 給 Codex 的說明

先讀同一層的 `CLAUDE.md`，那份是主要的安裝指示，裡面關於「怎麼跟不會寫程式的人講話」「裝之前先問哪三件事」「裝完要提醒重開」的部分，在這裡一樣適用。

這份檔案只補充 Codex 跟 Claude Code 不一樣的地方。

## hooks 不能照搬

`hooks/` 底下那三支是照 Claude Code 的機制寫的，直接複製到 Codex 環境不會動。

**先更正一件事**：這份文件原本寫「事件名稱不一樣」，那是錯的。Codex 的 hooks 一樣用 `PreToolUse`、`PostToolUse`、`SessionStart`、`Stop`、`UserPromptSubmit`、`PermissionRequest`、`SubagentStart`、`SubagentStop` 這些名字，連 `matcher` ＋ `hooks` 的結構都一樣。真正要改的是下面這幾項。

| | Claude Code | Codex |
|---|---|---|
| 設定放哪 | `settings.json` 裡的 `hooks` 區塊 | 獨立的 `~/.codex/hooks.json`，另外 `config.toml` 要有 `hooks = true` |
| matcher 裡的工具名 | `Write`／`Edit`／`MultiEdit`／`Bash`／`WebFetch` | 改檔案是 `apply_patch`，執行指令是 `exec`／`shell`／`exec_command`，抓網頁是 `web_fetch`。寫成 `apply_patch\|Write\|Edit\|MultiEdit` 這種兩邊都涵蓋的形式最省事 |
| 環境變數 | `CLAUDE_PROJECT_DIR`（`lint-gate.sh` 有用到） | 沒有這個，要換成別的取法 |
| 信任機制 | 無 | hook 要先被信任才會執行，第一次啟用要確認 |
| 事件涵蓋範圍 | 另有 `PreCompact`、`SessionEnd`、`Notification` 等 | 另有 `PostCompact`。兩邊各有對方沒有的事件，移植前先確認你要掛的那個存不存在 |

**還有一項沒被驗證過**：傳進腳本的那包 JSON 欄位（`tool_name`、`tool_input`、`session_id`、`stop_hook_active`、`last_assistant_message`）在 Codex 是不是同名，我沒有實測過。移植時務必實跑一次確認腳本真的讀到值——**不要看它沒報錯就當成生效了**，那正是這三支 hook 想防的事。

所以遇到使用者拿這包給 Codex 裝的時候，**先講清楚這件事，不要照抄然後宣稱裝好了**。

可行的做法有兩條，讓使用者選：

1. 只裝 `skills/`，那部分是純文字的做事步驤，兩邊通用。
2. 你依照 Codex 現行的機制，把那三支的判斷邏輯重寫一遍。原理很簡單（記帳、對帳、比對文字），重寫不難，但要實際測過再說裝好了。

## skills 可以直接用

`skills/` 底下的六個資料夾都是純文字說明，沒有綁定任何平台。放進 Codex 讀得到的位置即可。

review-loop 例外一半：SKILL.md 本身通用，但它帶了一支 Python 腳本與一份 HTML 模板，整包一起複製，並把 SKILL.md 裡「指令」那段的路徑改成實際安裝位置。腳本只用標準函式庫，跟哪個助手無關。

checkpoint 跟 neat-freak 裡面提到的「子代理」在 Codex 有對應的做法，設定的名稱不一樣，照你這邊的慣例調整。

## 不要假裝裝好了

這整包東西的主題就是「不要相信沒有證據的完成宣稱」。你在幫別人裝的時候更不能犯這個錯。

裝不了的部分講清楚裝不了，重寫過的部分講清楚你改了什麼，測過才說能動。
