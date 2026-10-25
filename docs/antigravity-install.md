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

Antigravity 的 `PreToolUse` hook 在工具執行前觸發，可以回 `{"decision": "deny"}` 否決；`Stop` hook 在執行迴圈結束時觸發，回 `{"decision": "continue"}` 可以擋下結束、讓 agent 繼續（官方文件：`agy` 內建的 `agy-customizations/docs/hooks.md`）。所以防呆類 hook 在這裡有真正的攔截點。本 repo 為 6 個選裝 hook 提供 Antigravity 登記：

```bash
# 預覽（不寫任何檔案）
python scripts/install.py --dry-run --agent antigravity --hooks danger-zone-guard,test-gate-guard,no-emoji-guard,claim-guard,lint-gate
# 正式安裝
python scripts/install.py --agent antigravity --hooks danger-zone-guard,test-gate-guard,no-emoji-guard,claim-guard,lint-gate
# 另外還有 anti-doom-loop-guard；--hooks all 就是這 6 個
python scripts/install.py --agent antigravity --hooks anti-doom-loop-guard
```

### 每個 hook 在 Antigravity 的做法

工具名是 step type 的小寫。每個 hook 與 Claude Code 版本是**同一支腳本**，用 Antigravity 專有欄位（`toolCall`、`conversationId`）辨認呼叫端，Claude／Codex／Cursor 的行為不變。

| hook | 事件 | matcher | 攔截方式 | 說明 |
|---|---|---|---|---|
| `danger-zone-guard` | `PreToolUse` | `run_command` | deny | 讀 `toolCall.args.CommandLine`，規則同 Claude 版 |
| `test-gate-guard` | `PreToolUse` | `run_command` | deny | 同上：`pytest ; git push` 擋、`&&` 放行 |
| `no-emoji-guard` | `PreToolUse` | `write_to_file\|replace_file_content\|multi_replace_file_content` | deny | 檢查 `CodeContent`、`ReplacementContent`、`ReplacementChunks[].ReplacementContent`，路徑看 `TargetFile`；`no-emoji-guard.json` 放在腳本旁 |
| `claim-guard`（記帳） | `PostToolUse` | `run_command\|grep_search\|find_by_name\|list_dir\|write_to_file\|replace_file_content\|multi_replace_file_content` | 只記錄，回 `{}` | 記下跑過哪些驗證指令、做過哪些搜尋、改過哪些檔（改檔晚於最後一次驗證，查驗端視為驗證過期）；`error` 非空（工具失敗）的呼叫不記，失敗的測試不算證據 |
| `claim-guard`（查驗） | `Stop` | 無（Stop 不用 matcher） | continue | 見下方「限制」第 1 點：**能攔，但取不到訊息的方式未被官方文件保證** |
| `lint-gate` | `Stop` | 無 | continue | 專案根目錄（`workspacePaths[0]`）有 `.lint-gate.json` 才會跑；失敗時把輸出交回 agent |
| `anti-doom-loop-guard` | `PreToolUse` | `run_command\|view_file\|write_to_file\|replace_file_content\|multi_replace_file_content` | deny | 同一個 `run_command` 或 `view_file` 連續 3 次、中間沒有別的工具呼叫才否決；改檔工具讓計數歸零 |

| 輸出 | 格式 |
|---|---|
| 否決（`PreToolUse`） | stdout `{"decision":"deny","reason":"..."}`，exit 0 |
| 擋下結束（`Stop`） | stdout `{"decision":"continue","reason":"..."}`，exit 0 |
| 放行 | `PreToolUse` 回 `{"decision":"ask"}`，交給 Antigravity 原本的權限流程（官方規定 `decision` 必填，回空的 `{}` 會被當成否決、原因空白，所有指令都會被擋）；不回 `allow`，那會自動核准、跳過你仍想要的授權彈窗。`PostToolUse` 與放行的 `Stop` 回 `{}` |

> 這一版之前，`danger-zone-guard`、`test-gate-guard`、`no-emoji-guard` 對 Antigravity 放行時回的是 `{"decision":"allow"}`，現在改為 `{"decision":"ask"}`（曾短暫改成 `{}`，會讓所有 `run_command` 被擋，已修正）。

### 登記格式

`~/.gemini/config/hooks.json` 的**頂層 key 是 hook 名稱**，底下才是事件，與 Claude Code 的巢狀 `hooks` 區塊不同。兩種事件的形狀也不同：

```json
{
  "danger-zone-guard": {
    "PreToolUse": [
      { "matcher": "run_command",
        "hooks": [ { "type": "command", "command": "python C:\\Users\\<你>\\.gemini\\config\\hooks\\danger_zone_guard.py", "timeout": 10 } ] }
    ]
  },
  "lint-gate": {
    "Stop": [
      { "type": "command", "command": "python C:\\Users\\<你>\\.gemini\\config\\hooks\\lint_gate.py", "timeout": 60 }
    ]
  }
}
```

`PreToolUse` / `PostToolUse` 是 `{matcher, hooks:[...]}` 分組；`Stop` 是**扁平**的 handler 清單，沒有 matcher、沒有 `hooks` 包一層。把 `Stop` 寫成分組（Claude Code 的寫法）是舊的 Claude 版面檔案被整份拒絕的可能原因之一（`invalid hook "hooks": command hook must specify 'command'`）。

| 項目 | 內容 |
|---|---|
| 腳本 | `~/.gemini/config/hooks/`（平放，hook 之間不互相 import） |
| 備份 | 先備份到 `~/.gemini/backups/hooks.json.bak-<時間>`；寫完讀回驗證；重跑不重複 |
| 合併 | 只加自己那幾筆；其他 hook 名稱與你自己的內容原樣保留；已存在的同名登記（例如手動加的 `anti-doom-loop-guard`）視為已安裝、不重複 |
| 拒絕寫入 | 檔案頂層有 Claude Code 版面的 `hooks` 區塊，或任何 entry 的形狀 Antigravity 會拒絕（例如 `Stop` 被包成 matcher 分組）時，安裝器印 `REFUSED` 與原因，**不複製檔案、不備份、不寫入**，因為 Antigravity 會整份拒絕，寫進去只會得到「安裝成功但從不執行」。請先把該區塊搬出檔案（保留備份）再重跑 |
| 不帶 `--hooks` | Antigravity 只裝 skills |

**命令不加引號、路徑不能有空白。** Antigravity 內建文件寫命令經 `cmd /c`（Windows）或 `sh -c` 執行，但已知有版本自己切 argv、不處理引號；不加引號、路徑沒有空白，兩種情況都能跑。所以安裝器寫的是 `python C:\Users\<你>\.gemini\config\hooks\anti_doom_loop_guard.py` 這種形式。路徑含空白或引號時安裝器直接拒絕並說明，請用 `--gemini-dir` 指到沒有空白的位置。

### 限制與沒做的

1. **`claim-guard` 的查驗端拿不到助理訊息。** `Stop` payload 只有 `conversationId`、`transcriptPath`、`terminationReason` 等，沒有最後一則訊息，所以腳本去讀 `transcriptPath` 指的檔案。官方 hooks 文件沒有描述那個檔案的行格式；腳本照 `run-workflow` 文件記載的 step 形狀（`type: PLANNER_RESPONSE`、`text`）去讀，讀不到模型訊息就放行（fail-open），所以格式不同時它是「沒作用」而不是「誤擋」。`verify-install.py` 用符合該形狀的合成 transcript 驗證，只證明 adapter 邏輯，**不證明真實 transcript 讀得到**，請在真實 session 看過它擋一次再信任。
2. **`Stop` 沒有 `stop_hook_active`。** Claude Code 靠它避免無限擋下；Antigravity 沒有，所以 `claim-guard` 與 `lint-gate` 用「同一則訊息／同一份失敗輸出只擋一次」的指紋（存在暫存目錄，可用 `HARNESS_GUARD_STATE_DIR` 改位置）：agent 原封不動再試一次就放行，改了內容或失敗輸出變了才會再擋；乾淨通過就清掉。
3. 只在 `terminationReason` 是 `NO_TOOL_CALL` 或 `TERMINAL_STEP_TYPE`（正常結束）時檢查；使用者取消、錯誤、達上限都直接放行。
4. 除 `run_command.CommandLine` 外，工具參數名稱（`TargetFile`、`CodeContent`、`ReplacementContent`、`ReplacementChunks`）官方 hooks 文件沒列；沿用本 repo 既有 `no-emoji-guard` 對 Antigravity 的處理，請以實測為準。
5. `view_file` 的參數名稱官方文件沒列；`anti-doom-loop-guard` 把整組參數當簽章，不依賴特定名稱。
6. **herdr 的 `herdr-agent-state.ps1` 不在這裡**：它是 herdr 自己的整合，用到 `UserPromptSubmit`、`Notification`、`SessionEnd` 等 Antigravity 沒有的事件，本安裝器不處理也不會動它。
7. `fork_pr_guard` 不在本 repo（維護者自己的 hook），所以這裡不登記。

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

對 `hooks.json` 裡登記的每個本 repo hook，它會檢查登記格式（頂層沒有 Claude 版面的 `hooks` 區塊、`Stop` 是扁平清單、命令無引號、matcher 涵蓋該 hook 要看的工具、腳本存在），再用 Antigravity 形狀的 payload live-fire，一次放行、一次攔截：

- `danger-zone-guard`：`rm -rf /` 否決、`rm -rf dist/` 回 ask；`test-gate-guard`：`pytest ; git push` 否決、`&&` 回 ask；
- `no-emoji-guard`：含 emoji 的 `write_to_file` 否決、乾淨內容回 ask；
- `claim-guard`：空帳本時 `Stop` 回 continue，記一次 `pytest -q` 之後同樣的話放行（transcript 是合成的，見上方限制第 1 點）；
- `lint-gate`：沒有 `.lint-gate.json` 的專案回 `{}`、檢查失敗回 continue、同一份失敗第二次放行；
- `anti-doom-loop-guard`：改檔夾在中間不擋、連續 3 次相同指令擋。
