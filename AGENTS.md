# 給 Codex 的說明

先讀同一層的 `CLAUDE.md`，那份是主要的安裝指示，裡面關於「怎麼跟不會寫程式的人講話」「裝之前先問哪三件事」「裝完要提醒重開」的部分，在這裡一樣適用。

這份檔案只補充 Codex 跟 Claude Code 不一樣的地方。

## hooks 現在有 Codex 版了

`hooks/<工具名>/codex/` 底下就是。三支都有，判斷邏輯跟 Claude Code 版一模一樣，介面的部分已經改好，**直接複製到 `~/.codex/hooks/` 就能用，不用自己移植**。

安裝步驟：

1. 複製 `hooks/<工具名>/codex/` 底下的腳本到 `~/.codex/hooks/`，`chmod +x`
2. 把 repo 根目錄 `codex-hooks-example.json` 需要的區塊併進 `~/.codex/hooks.json`（已有同名事件就把 hooks 陣列的內容加進去，不要整段覆蓋）
3. 確認 `~/.codex/config.toml` 有 `hooks = true`
4. Codex 對 hook 有信任機制，第一次啟用要確認
5. 重開 session

**裝完要實際觸發一次確認它真的有反應**，不要看它沒報錯就宣稱裝好了。

兩邊的介面差異、以及想自己移植其他 hook 時要改什麼，見 `hooks/README.md` 的對照表。簡短版：事件名稱兩邊一樣，要改的是 `session_id` → `turn_id`、matcher 補 `apply_patch`／`exec`／`shell`、沒有 `CLAUDE_PROJECT_DIR` 改讀 payload 的 `cwd`、放行時要印 `{}`、擋下來是回 `{"decision":"block","reason":...}` 而不是 exit 2。

## skills 可以直接用

`skills/` 底下的六個資料夾都是純文字說明，沒有綁定任何平台。放進 Codex 讀得到的位置即可。

review-loop 例外一半：SKILL.md 本身通用，但它帶了一支 Python 腳本與一份 HTML 模板，整包一起複製，並把 SKILL.md 裡「指令」那段的路徑改成實際安裝位置。腳本只用標準函式庫，跟哪個助手無關。

checkpoint 跟 neat-freak 裡面提到的「子代理」在 Codex 有對應的做法，設定的名稱不一樣，照你這邊的慣例調整。

## 不要假裝裝好了

這整包東西的主題就是「不要相信沒有證據的完成宣稱」。你在幫別人裝的時候更不能犯這個錯。

裝不了的部分講清楚裝不了，重寫過的部分講清楚你改了什麼，測過才說能動。
