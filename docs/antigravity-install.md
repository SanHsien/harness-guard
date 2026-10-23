# Google Antigravity (AGY) 安裝與整合指南

> [English](antigravity-install.en.md) | 中文版

Google Antigravity (AGY) 擁有先進的 Customization System（自訂義系統），包含規則（Rules）、技能（Skills）、掛鉤（Hooks）與插件（Plugins）。本指南說明如何將 `harness-guard` 整合進 Antigravity 環境。

---

## 快速安裝（一行指令）

在終端機中執行：

```bash
# 預覽將安裝的技能
python scripts/install.py --agent antigravity --dry-run --skills all

# 正式安裝所有技能至 ~/.gemini/config/skills/
python scripts/install.py --agent antigravity --skills all
```

此指令會將 `skills/` 底下的所有技能資料夾完整複製到 Antigravity 的全域技能目錄（`~/.gemini/config/skills/`），Antigravity 會以**漸進式揭露 (Progressive Disclosure)** 自動探索並載入。

---

## Hooks（選裝）

Antigravity 的 `PreToolUse` hook 在工具執行前觸發，可以回 `{"decision": "deny"}` 否決，所以防呆類 hook 在這裡有真正的攔截點（官方文件：`agy` 內建的 `agy-customizations/docs/hooks.md`）。本 repo 目前只提供一個 Antigravity 登記：

```bash
python scripts/install.py --dry-run --agent antigravity --hooks anti-doom-loop-guard
python scripts/install.py --agent antigravity --hooks anti-doom-loop-guard
```

| 項目 | 內容 |
|---|---|
| 腳本 | `~/.gemini/config/hooks/anti_doom_loop_guard.py` |
| 登記 | `~/.gemini/config/hooks.json`，**頂層 key 是 hook 名稱**（`anti-doom-loop-guard`），底下才是事件；與 Claude Code 的巢狀 `hooks` 區塊不同 |
| 事件 / matcher | `PreToolUse`，`run_command\|view_file\|write_to_file\|replace_file_content\|multi_replace_file_content`（工具名是 step type 的小寫） |
| 行為 | 同一個 `run_command` 或 `view_file` 連續 3 次、中間沒有別的工具呼叫才否決；改檔工具讓計數歸零 |
| 否決格式 | stdout `{"decision":"deny","reason":"..."}`，exit 0 |
| 放行格式 | stdout `{}`。不回 `{"decision":"allow"}`：Antigravity 的 `allow` 是「自動核准這次呼叫」，會跳過你仍想要的授權彈窗 |
| 備份 | 先備份到 `~/.gemini/backups/hooks.json.bak-<時間>`；寫完讀回驗證；重跑不重複 |

安裝器只加自己那一筆，其他 hook 名稱與你自己的內容原樣保留。不帶 `--hooks` 時 Antigravity 只裝 skills；`--hooks all` 只會裝有 Antigravity 登記的 hook，其餘名稱會印一行說明並略過。

**命令不加引號、路徑不能有空白。** Antigravity 內建文件寫命令經 `cmd /c`（Windows）或 `sh -c` 執行，但已知有版本自己切 argv、不處理引號；不加引號、路徑沒有空白，兩種情況都能跑。所以安裝器寫的是 `python C:\Users\<你>\.gemini\config\hooks\anti_doom_loop_guard.py`。路徑含空白或引號時安裝器直接拒絕並說明，請用 `--gemini-dir` 指到沒有空白的位置。

已知限制：

- `view_file` 的參數名稱官方文件沒列；腳本把整組參數當簽章，不依賴特定名稱，所以不會把分頁讀取誤判成重試。
- 其餘 5 個 hook（claim-guard、test-gate-guard、danger-zone-guard、lint-gate、no-emoji-guard）目前沒有 Antigravity 登記，安裝器不會替它們寫 `hooks.json`。
- 若你的 `hooks.json` 頂層已有 Claude Code 版面的 `hooks` 區塊，安裝器會提醒並原樣保留；Antigravity 曾有一個版本因為這種檔案報 `invalid hook "hooks"`，請以 `agy` 實際載入結果為準。

---

## Antigravity 規則檔整合 (GEMINI.md)

Antigravity 支援階層式規則載入（Global: `~/.gemini/GEMINI.md`，專案層級: 專案根目錄的 `GEMINI.md` 或 `.agents/rules/*.md`）。

1. 參考本 repo 中的 `gemini-md-template/GEMINI.md`。
2. 將其內容合併至你的 `~/.gemini/GEMINI.md` 或當前專案根目錄。
3. 可選的專項規則（如 `gemini-md-template/rules/`）可直接放入 `.agents/rules/` 或 `~/.gemini/config/rules/`。

---

## 信任工作區與免彈窗設定

不想被授權彈窗一直打斷的話，編輯 `~/.gemini/antigravity-cli/settings.json`。

**先看清楚這是什麼交易。** 關掉彈窗等於把「人按確認」這道關卡拿掉，剩下唯一擋在 agent 與
你檔案之間的就是這包 hook。這也正是這包東西存在的理由——但那是攔截器，不是沙箱。
它擋掉的是幾類已知的災難指令，不是所有壞事。範圍開多大，風險就多大。

信任路徑**只給你放專案的資料夾**，不要給整個家目錄。家目錄底下有 SSH 金鑰、瀏覽器
資料、憑證與你所有的私人檔案，沒有理由納進來：

```json
"trustedWorkspaces": [
  "C:\\Users\\<你的使用者名稱>\\Documents\\GitHub"
]
```

自動執行的部分，建議分兩段開。先開不會改到東西的：

```json
"agent_features": {
  "auto_run_tests": true,
  "smart_context_retrieval": true,
  "web_search_enabled": true,
  "browser_testing_enabled": true,
  "mcp_enabled": true
}
```

用一陣子確定 hook 真的會擋（`verify-install.py` 綠燈、而且你**親眼看它擋下來過**）再考慮
下面這三個。它們一開，檔案改寫與指令執行就沒有人工確認了：

```json
"auto_approve_commands": true,
"auto_approve_file_edits": true,
"skip_permission_prompts": true,
"auto_execution_mode": "full_auto"
```

---

## 驗證安裝

執行以下指令進行安裝自我驗證：

```bash
python scripts/verify-install.py --agent antigravity
```

已登記 `anti-doom-loop-guard` 時，它會檢查登記格式（無引號、matcher）並用 Antigravity 形狀的 payload live-fire：改檔夾在中間不擋、連續 3 次相同指令擋。
