> [English](CHANGELOG.en.md) | 中文版

# 變更紀錄

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，新的在上面。
`fork` 標記的是本 fork 相對於
[上游](https://github.com/agentcrew-academy/harness-starter-kit) 的改動。

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
