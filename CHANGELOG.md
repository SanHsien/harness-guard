> [English](CHANGELOG.en.md) | 中文版

# 變更紀錄

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，新的在上面。
`fork` 標記的是本 fork 相對於
[上游](https://github.com/agentcrew-academy/harness-starter-kit) 的改動。

---

## 2026-08-18

### 新增

- **`fork` `install.py --agent cursor` 與 `--agent codex`。** Cursor 寫入扁平的 `~/.cursor/hooks.json`（`version: 1` + event → `[{command}]`），shell 守衛掛在 `beforeShellExecution`，emoji 掛在 `preToolUse`。Codex 合併進既有 `~/.codex/hooks.json`，Windows 使用 Python 版與絕對路徑，避免 `python3 ~/.codex/hooks/...` 無聲失敗。`--agent all` 現在包含這兩個 target。
- **`fork` docs/cursor-install.md**（+ `.en.md`）：事件對照，以及 Cursor `stop` 不能否決、只能 follow-up 的限制。

### 變更

- **`fork` `verification-protocol` 新增有界 live validation。** UI、Production、OAuth、部署與外部服務驗證現在會先定義最小證據清冊與停止條件，限制為一筆唯一 smoke data、精準查詢、一次控制恢復與登入後原地續做，達標即停，避免重複驗證耗用真實資料與 quota。
- **`fork` Codex skill 安裝位置對齊現行契約。** `install.py --agent codex` 現在寫入 `~/.agents/skills/`，不再建立新的 legacy `~/.codex/skills/`；既有 legacy 內容保留。Codex 文件與 verifier 也明確區分腳本 live-fire 與 `/hooks` trust 檢查。
- **`fork` Codex 安裝驗證改為真實 payload live-fire。** verifier 現在會執行 5 種已註冊的 Codex hooks，缺少腳本會失敗，不再只驗 `hooks.json`。no-emoji-guard 也補讀真實 `apply_patch` payload 的 `tool_input.command`，只掃新增行並保留 transcript / `.srt` 路徑豁免，避免註冊正常卻 fail-open，或反過來攔住 emoji 移除。
- **`fork` POSIX hook 安裝會正規化為 LF。** 即使從 Windows CRLF checkout 在 WSL 執行安裝器，複製到 agent 目錄的 `.sh` 也不會因 `set: invalid option` 而失效；`.gitattributes` 同步固定 shell scripts 使用 LF。
- **`fork` Python hook 讀 Cursor payload。** `beforeShellExecution` 的指令在頂層 `command`，工具名是 `Shell`。擋下時回 `{"permission":"deny"}`；Claude Code 的 `exit 2` + stderr 與 Codex 的 `decision` JSON 維持不變。
- **`fork` Cursor `stop` 上的 claim-guard / lint-gate 改 follow-up。** Cursor 不能在回合結束後 veto，硬擋會假裝有保護。沒有 `last_assistant_message` 時 claim-evidence 仍 fail-open（與既有契約相同）。
- **`fork` lint-gate 的專案目錄也可來自 payload `cwd` / `workspace_roots`。** Cursor 使用者層 hook 的行程 cwd 是 `~/.cursor`，不能只用 `os.getcwd()`。

---

## 2026-08-15

### 修正

- **`fork` `--dry-run --agent antigravity/all` 現在真的零寫入。** 原本 `install.py` 在 dry-run 模式仍會建立 `~/.gemini/config/skills/`，與「nothing will be written」契約矛盾；現在只有正式安裝才會建立目錄，並加入跨平台 regression test 鎖住此行為。
- **`fork` 所有 hook 改用 bytes 讀取 payload，中文觸發詞才真的會動。**
  原本九支 hook 都用 `json.load(sys.stdin)`，那會依 locale 決定解碼方式。在繁體中文
  Windows（cp950）上，claim-evidence-guard 收到「我已經驗證通過，測試全數通過」卻直接放行——
  預設 locale 與嚴格 cp950 兩種情況都一樣。**這個 kit 標榜雙語，但中文那一半從來沒生效過**，
  而且是 fail-open，所以外表看不出任何異狀。
  發現方式是對執行中的 Stop hook 下探針：2.3 KB 的 payload 解析成空物件，guard 根本沒看到訊息；
  同一份 payload 改讀 bytes 就完整解出 11 個欄位。
  新增 `hooks/tests/run-encoding-tests.py`，在 `PYTHONIOENCODING=cp950` 下餵含中文的 payload
  給每支 hook，6 案全過，並確認對舊版會失敗。
- **`fork` claim-guard 帳本每行寫入後 fsync。** PostToolUse hook 是短命行程，緩衝寫入還沒落地
  就被回收，會產生 0 bytes 的帳本——下游讀起來是「沒有證據」，於是 claim-evidence-guard 反過來
  誤擋真的跑過測試的宣稱。空帳本比沒有帳本更糟。
- **`fork` danger-zone-guard 補掉引號繞過。** `rm -rf "/"`、`rm -rf "$HOME"`、`rm -rf '~'`
  原本全部放行：它沿用了 test-gate-guard 的「挖空引號」做法，但那裡引號內是**提到指令的文字**，
  這裡引號內是**真正要刪的路徑**。改為刪除類先去引號、且只認指令位置（行首或 `;`、`&&`、`||`、
  pipe 之後，允許 `sudo`）；強推與外洩類維持挖空引號，避免 commit message 被誤判。
- **`fork` 移除 danger-zone-guard 的 Windows shim。** 它靠 import 隔壁資料夾，但 hook 是平放安裝，
  裝完會 import 到自己：AttributeError，每次 Bash 呼叫 exit 1 且什麼都不擋。改用單一跨平台檔。
  **通則：平放安裝代表 hook 之間不可以互相 import。**

### 變更（上游）

- **編碼修正已送回上游並被接受**（[upstream#2](https://github.com/agentcrew-academy/harness-starter-kit/pull/2)）。
  上游接著補上 stdout／stderr 也要設成 UTF-8——hook 可能正確擋下、卻在印自己的訊息時
  因為 locale 編碼炸掉，使用者看到 traceback 而不是原因。該改法已拉回本 fork 的全部九支 hook。

### 新增（設定持久化）

- **`fork` no-emoji-guard 的設定改放腳本旁的 `no-emoji-guard.json`，重裝洗不掉。**
  起因是實際事故：安裝程式整支覆蓋 hook 腳本，把使用者刻意關掉的設定洗回「開啟」，而且無聲。
  現在支援 `{"enabled": false}`（保持安裝但關閉，開回去只要改一個字、即時生效不用重啟）與
  `{"exempt_path_substrings": [...]}`，優先於腳本內的常數；設定檔壞掉時回到內建預設（繼續擋），
  打錯字不該變成關掉護欄的方式。兩個平台版本各 5 案回歸測試，並納入 CI。

### 修正（安裝器：重複註冊）

- **同一支腳本改了參數後會被重複註冊。** 加上 `--codex` 讓指令字串變了，安裝器的比對是整串
  比對，於是把新的加在舊的旁邊——lint-gate 與 claim-ledger-tracker 在 Codex 上每次事件跑兩次，
  其中一次還是用舊行為。在真實機器上發生過（2026-08-20）。
  改為以**腳本路徑**比對：同一支腳本的舊註冊會被移除再寫入新的；清理無條件執行
  （不是只在「有新增」時），而且有清理就會寫回檔案，否則清掉的東西根本沒落地。
  使用者自己的其他 hook 不受影響。附回歸測試（連跑兩次驗證冪等）。

### 修正（跨 agent 協定）

- **Cursor 支援誤把 Claude Code 認成 Cursor，兩支 Stop 守衛因此不再攔截。**
  判斷式是 `payload.get("hook_event_name")`，但那個欄位 Claude Code 也會送（大寫的 `Stop`、
  `PreToolUse`）。於是 claim-evidence-guard 與 lint-gate——正好是「不准結束回合」那兩支——
  改印 Cursor 的 follow-up JSON 並回傳 0，在它們主要保護的平台上等於不再擋。
  既有測試抓不到，因為合成 payload 沒有 `hook_event_name`。
  改為只認 `cursor_version` 或 Cursor 自己的事件名（小寫 `stop`、`beforeShellExecution` 等）。
- **Codex 在 Windows 上裝到的是 claude-code 版 hook，協定不對。** test-gate、danger-zone、
  no-emoji 三支本來就有純 Python 的 codex 版，Windows 完全能跑，只是沒被選用；結果攔截時
  exit 2 且不印 JSON，Codex 讀不到。已改指向 codex 版。
- **lint-gate 與 claim-ledger-tracker 沒有免 jq 的 codex 版**，改由安裝器加 `--codex` 參數，
  讓 Windows 版用 Codex 的 JSON 協定回應（放行印 `{}`、攔截印 `decision: block`）；
  不加參數時 Claude Code 行為完全不變。
- 新增 `hooks/tests/run-agent-protocol-tests.py`（12 案，已進 CI）：用**貼近真實**的 payload
  驗證每支 hook 對三種 agent 各自回應正確的協定。已確認對修正前的版本會紅燈（2 案）。

### 修正（安裝器）

- **Windows 唯讀檔導致的 `PermissionError` 已處理**：`robust_rmtree` 會清掉唯讀位元再刪。
  git checkout 或編輯器留下的唯讀檔會讓 `shutil.rmtree` 直接噴錯。
- **但刪不掉時不再假裝成功。** 原本的寫法把錯誤 `except Exception: pass` 吃掉，接著用
  `dirs_exist_ok=True` 蓋上去：結果是舊版殘留檔留著、卻印出「copied」、exit 0。實測（檔案被
  另一個行程開啟時）確認會發生。現在改成明確報 `FAILED to replace`、整個資料夾原封不動、
  不印「Installation finished」、exit 1——exit code 也必須反映事實，否則 `&&` 串接會照樣往下走。
  兩案回歸測試進 CI（唯讀→修好並替換；鎖住→報失敗不宣稱），並確認對修正前的版本會紅燈。

### 修正（回歸）

- **`fork` 兩支 hook 被改回文字模式讀 stdin，已修回並加靜態檢查。** 新增 Antigravity 生命週期
  支援的那次改動，把 `read_payload()` 留在檔案裡但不再從 `main()` 呼叫——helper 成了孤兒，
  hook 悄悄退回依 locale 解碼。編碼測試當場抓到（2 案紅燈）。
  同時發現：用 grep 找 `stdin.buffer` **證明不了任何事**，那只證明字串存在。
  `hooks/tests/run-encoding-tests.py` 因此加了一道 AST 靜態檢查：任何 hook 只要真的呼叫
  `sys.stdin.read()`／`json.load(sys.stdin)`，或定義了 `read_payload()` 卻沒用，就紅燈。
  （用 AST 不用 grep，因為這些檔案的 docstring 本來就會提到那兩個呼叫，正是為了說明不要用。）

### 變更（文件）

- **`fork` 兩套新技能與 `gemini-md-template/` 改寫成英文**，與既有九套技能、`claude-md-template/`
  一致（那些檔案是給 agent 讀的，repo 內統一英文；`README`、`docs/` 仍以中文為主、英文放 `.en.md`）。
- **`fork` `gemini-md-template/GEMINI.md` 依它自己宣稱的減法原則重寫。** 原版寫了五段，其中包含
  深色模式、玻璃擬態、指定字型這類**個人審美**，以及會過期的語言版本號。拿掉這一行 AI 會不會犯錯？
  不會——那就不該出現在一份「每個專案都會載入」的全域規則檔裡。現在是它 README 本來就宣稱的
  三段結構（背景／硬閘門／判斷脈絡），偏好改成待填空格。
- **`fork` Antigravity 安裝指南的自動化建議改掉。** 原本建議把整個家目錄設為信任工作區並一次
  打開全部自動核准。信任範圍縮到專案資料夾，並把「關掉彈窗＝這包 hook 成為唯一防線，而它是
  攔截器不是沙箱」講明，自動化拆成兩階段。

### 新增

- **`fork` 跨平台 CI**：Linux / Windows × Python 3.11 / 3.14 執行核心 Python compile、danger-zone/test-gate/encoding regression suites、installer dry-run 契約測試與完整 dry-run 計畫。
- **`fork` danger-zone-guard**（第五個攔截工具）：攔截根目錄／家目錄遞迴刪除、刪除 `.git`、
  保護分支強推、憑證外洩。附 25 案回歸測試（兩個平台版本）。
- **`fork` Google Antigravity (AGY) 支援**：`docs/antigravity-install.md`（+ `.en.md`）、
  `gemini-md-template/` 起手規則檔、`install.py` 支援多 agent 目標。
- **`fork` 兩套工作流程**：`verification-protocol`（修改即驗證、零偽修正）、
  `task-orchestrator`（Research → Plan → Build → Verify 四階段拆解與 context 管理）。
- **`fork` `scripts/install.py`**：一行指令重現整套環境。自動判平台、**合併**而非覆蓋設定檔、
  先備份、原子寫入、寫完讀回驗證 JSON 仍合法，重跑不會重複註冊，既有 skill 資料夾不覆蓋。
- **`fork` `scripts/verify-install.py`**：餵合成 payload 給每支已安裝的 hook、實際執行、檢查回應。
  「讀設定檔然後宣布沒問題」正是這個 kit 要擋的那種無證據宣稱。
- **`fork` test-gate-guard**（第四個攔截工具）：擋掉單條指令裡用 `;`（而非 `&&`）串接測試與
  `git commit`／`git push` 的紅燈出貨。來自一次真實事故，並附上它自己上線第一天誤報所產生的回歸測試。
- **`fork` Windows 版 hook**（`hooks/*/windows/`）：claim-guard 與 lint-gate 的純 Python 版。
  shell 版靠 `jq`，Windows 原生沒有 `jq`，而它們沒有 `jq` 時 `exit 0`——那代表「放行」。
- **`fork` lint-gate 專案級設定 `.lint-gate.json`**：全域註冊一次即可，沒有這個檔案的專案完全
  不受影響；要開的專案自己丟一個檔案，立即生效、不用重啟。
- **`fork` `docs/windows-install.md`**（+ `.en.md`）：Windows 三個無聲失敗模式與各自解法，
  每一項都在真實機器上實測過。

### 變更

- **`fork` README 改為產品／支援矩陣優先**：明確區分 Claude Code、Codex、Antigravity / Gemini、Cursor 的 hooks / skills / installer 能力；不再把 `--agent all` 說成 Codex / Cursor 也會自動註冊。
- **`fork` `AGENTS.md` 收斂為安裝安全不變式 + repo 維護規則**，保留非技術使用者安裝契約，但正常 repo 工作改為 branch → PR → CI → merge，純文件整理不再機械式要求 changelog / release。
- **`fork` `AGENTS.md` 改寫為單一真相源**，任何 AI agent 讀這一份就夠；`CLAUDE.md` 縮成
  Claude Code 專屬薄補丁。
- **`fork` 文件語言翻轉**：`README.md` 等以繁體中文為主，英文放 `*.en.md` 鏡像。
- **`fork` `.gitignore` 補 `__pycache__`**：上游誤追蹤了 6 個 `.pyc`。

---

## 2026-08-14（上游）

- 新增 `claude-md-template/`：照五代模型官方指引寫的 `CLAUDE.md` 起手範本，加三個可選規則檔。

## 2026-08-12（上游）

- 新增 info-diet 工作流程：盤點注意力實際流向，純本機運算。

## 2026-08-09（上游）

- 三個攔截工具都補上 Codex 版，判斷邏輯與 Claude Code 版相同。
- 新增 review-loop 工作流程：防止長文件反覆修訂時段落無聲消失。
