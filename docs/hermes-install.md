> [English](hermes-install.en.md) | 中文版

# Hermes 安裝

Hermes 沒有「把 JSON 從 stdin 餵給腳本」的 hook 協定。它在自己的行程裡呼叫外掛：

```
Hermes 要執行工具
      |
      v
pre_tool_call(tool_name="terminal", args={"command": "..."}, session_id=..., ...)
      |
      +-- 回傳 None                                   -> 照常執行
      +-- 回傳 {"action": "block", "message": "..."}  -> 不執行，訊息回給模型
```

所以本 repo 給 Hermes 的不是一組 hook 檔，而是一個外掛資料夾。

## 裝了什麼

```
<Hermes 家目錄>/plugins/harness-guard/
  __init__.py            轉接層（hooks/hermes-plugin/__init__.py）
  plugin.yaml
  danger_zone_guard.py   hooks/danger-zone-guard/claude-code/ 的原檔
  test_gate_guard.py     hooks/test-gate-guard/claude-code/ 的原檔
  fork_pr_guard.py       選用。不在本 repo；有就會被呼叫，安裝器不建立也不覆蓋
```

轉接層匯入旁邊那兩個檔，呼叫它們的 `inspect_command()` 與 `verdict()`。偵測規則只有一份，
Claude Code、Antigravity、Cursor 跑的就是同樣這兩個檔。

只涵蓋 `danger-zone-guard` 與 `test-gate-guard`。`claim-guard`、`lint-gate`、`no-emoji-guard`、
`anti-doom-loop-guard` 需要 Hermes 沒有對應的事件或資料，沒有移植。

## 安裝

```bash
python scripts/install.py --dry-run --agent hermes
python scripts/install.py --agent hermes
python scripts/verify-install.py --agent hermes
```

Hermes 家目錄的預設值：環境變數 `HERMES_HOME`，沒有就用 `~/AppData/Local/hermes`（Windows）或
`~/.hermes`。要指定別處用 `--hermes-dir`。

安裝器做的事：

1. 內容不同的既有檔先備份到 `<Hermes 家目錄>/backups/harness-guard-plugin/`。
2. 複製四個檔。
3. 用 `hooks/hermes-plugin/probe.py` 在另一個行程載入**已安裝**的外掛，照 Hermes 的方式呼叫，
   確認該擋的擋、該放的放。紅了就把原本的檔放回去，結束碼 1。
4. 讀 `config.yaml` 的 `plugins.enabled`，沒有列 `harness-guard` 就印警告。

**不寫 `config.yaml`。** 外掛要列在 `plugins.enabled` 才會被載入，請自己加。Hermes 的
`command_allowlist`、`approvals` 等審批設定，安裝器不讀也不改。

## 失敗時怎麼表現

- 共用檔不見、載入失敗：帶指令的工具呼叫**全部擋下**，訊息寫出缺哪個檔、怎麼重裝。
- 某個檢查丟例外：該次指令擋下，訊息帶例外內容。
- 不帶指令的工具呼叫（讀檔、搜尋等）不受影響。

寧可擋也不放：這個外掛原本那一版就是靜靜地少擋五種指令，直到 2026-11-19 盤點才被查出來。

## 限制

- 外掛在 Hermes **啟動時**載入。裝完之後，執行中的 gateway 還在用舊檔，重啟才換。
- `verify-install.py` 與 probe 證明的是「已安裝的檔案判定正確」，不是「執行中的 Hermes 已載入它」。
  要確認後者，在真實 session 讓它擋一次。
- 只讀參數裡的 `command`／`cmd`／`CommandLine`。Hermes 其他會執行程式的工具（例如直接跑一段程式碼的工具、
  排程內的腳本）不經過這裡。
- Hermes 自己還有一層審批（`config.yaml` 的 `command_allowlist`）。那一層若已永久放行某類指令，
  本外掛照擋；反過來，本外掛放行的指令仍會走那一層。

## 移除

刪掉 `<Hermes 家目錄>/plugins/harness-guard/`，並從 `plugins.enabled` 拿掉 `harness-guard`，重啟 Hermes。
要回到上一版，把 `backups/harness-guard-plugin/` 裡的備份複製回去（檔名是 `<原檔名>.bak-<時間>-<亂數>`）。
