# AGENTS.md

給 Claude Code、OpenAI Codex、Google Antigravity / Gemini、Cursor 與其他 AI coding agent 在這個 repo 工作時的主要指引。
Claude Code 專屬路徑與 hook 事件補充見 [`CLAUDE.md`](CLAUDE.md)；衝突時以本檔為準。

這份檔案有兩個用途：

1. 使用者把 repo 丟給 agent，請 agent 協助安裝 Harness Guard。
2. AI coding agent 維護 Harness Guard repo 本身。

## 專案定位

Harness Guard 是 cross-agent AI coding guardrails kit。核心產品是：

- 5 個可執行 guardrail hooks；
- 11 套可選 workflow skills；
- Claude / Gemini 規則檔範本；
- `scripts/install.py` 可重現安裝；
- `scripts/verify-install.py` 對已安裝 Claude Code hooks 做 live-fire 驗證。

本 repo fork 自 `agentcrew-academy/harness-starter-kit`，MIT 授權與 attribution 不得移除。fork 差異與同步原則見 [`FORK.md`](FORK.md) 與 [`NOTICE`](NOTICE)。

## 先確認支援範圍，不要誇大

目前自動化能力不是所有 agent 都相同：

| Agent | 目前自動化範圍 |
|---|---|
| Claude Code | `install.py` 可安裝 hooks + skills；`verify-install.py` 可 live-fire 已安裝 hooks |
| Google Antigravity / Gemini | `install.py --agent antigravity` 可安裝 skills；另有 `GEMINI.md` 範本 |
| OpenAI Codex | `install.py --agent codex` 合併進 `~/.codex/hooks.json`（Windows 用 Python 版與絕對路徑） |
| Cursor | `install.py --agent cursor` 寫入 `~/.cursor/hooks.json`（扁平格式）與 `~/.cursor/hooks/` |

`--agent all` 目前走 Claude Code + Antigravity + Cursor + Codex。Cursor 的 `stop` 不能否決已結束的回合；claim-guard 與 lint-gate 在那裡改為 follow-up。

## 協助一般使用者安裝時

如果對方只貼 repo 網址說「幫我裝」，預設他不熟 hook、JSON 或終端機：

- 先用白話說明會修改哪些設定、會攔什麼。
- 先跑 dry-run；不要直接修改全域 agent 設定。
- 不要一次裝所有東西再回報；先從對方真的需要的 guardrail 開始。
- 不要叫使用者手動覆蓋設定檔；需要改時由 agent 合併、備份、驗證。
- 使用者想停用或移除就照做，不要勸留。

### 先問的重點

一次確認即可：

1. 使用哪個作業系統與 agent。
2. 最在意哪一類問題：無證據完成宣稱、危險指令、測試紅燈仍提交、lint、emoji。
3. 是否只要 hooks，或也需要 workflow skills / 規則檔。

## 安裝安全不變式

- **dry-run 不得寫入任何檔案或建立設定目錄。**
- 設定檔一律 merge，不覆蓋整份。
- 正式修改 Claude Code `settings.json` 前先備份，寫完重新以 UTF-8 解析驗證。
- 同名 skill 預設不覆蓋；只有使用者明確要求時才用 `--force`。
- 不提交 API key、token、私鑰、真實 `.env`、使用者設定或 agent session 資料。
- hook 安裝後是平放檔案，**hook 之間不得靠相對路徑互相 import**。
- 不宣稱 guardrail 是 sandbox、完整安全政策或百分之百攔截；它們是 pattern-based defense-in-depth。

## 平台選擇

### Windows

Claude Code 使用 Python 版本；先讀 [`docs/windows-install.md`](docs/windows-install.md)。

不要把依賴 `jq` 的 shell 版直接註冊到原生 Windows。缺 `jq` 時部分 shell hook 會 fail-open；裸 `bash` 也可能落到 WSL 而不是 Git Bash。

### macOS / Linux

Claude Code 可使用 repo 內的 POSIX / shell 實作；需要 `jq` 的 hook 必須先確認 `jq` 存在。

## 安裝指令

### Claude Code

```bash
python scripts/install.py --dry-run --hooks all --skills all
python scripts/install.py --hooks all --skills all
```

### Antigravity / Gemini skills

```bash
python scripts/install.py --dry-run --agent antigravity --skills all
python scripts/install.py --agent antigravity --skills all
```

### 目前所有自動化 target

```bash
python scripts/install.py --dry-run --agent all --hooks all --skills all
python scripts/install.py --agent all --hooks all --skills all
```

### Cursor

```bash
python scripts/install.py --dry-run --agent cursor --hooks all --skills all
python scripts/install.py --agent cursor --hooks all --skills all
```

### Codex

```bash
python scripts/install.py --dry-run --agent codex --hooks all --skills all
python scripts/install.py --agent codex --hooks all --skills all
```

## Hook 安裝注意事項

- `claim-guard` 的 tracker 與 evidence guard 必須一起安裝。
- `lint-gate` 沒有檢查指令就沒有實際價值；Windows 可全域註冊後由專案 `.lint-gate.json` 啟用。
- `no-emoji-guard` 是偏好型規則，不是安全必需品。
- `danger-zone-guard` 只攔明確定義的危險模式；不要把它描述成一般 shell sandbox。
- Codex hook 由 `install.py --agent codex` 合併進 `~/.codex/hooks.json`；Windows 必須用絕對路徑的 Python 版，不要註冊 `python3 ~/.codex/hooks/...`。
- Cursor hook 由 `install.py --agent cursor` 寫入扁平的 `~/.cursor/hooks.json`。不要把 Claude Code 的 nested `hooks[].hooks[]` 結構寫進 Cursor。

## 規則檔範本：merge，不是覆蓋

`claude-md-template/` 與 `gemini-md-template/` 是起手範本。

- 有既有規則檔時只併入適用項目，不整份覆蓋。
- 範本中的 placeholder 要實際填完；不要留下空白規則。
- 新增規則前先問：沒有這條，agent 是否真的會犯一個具體錯誤？
- 規則檔靠減法維護，不把所有偏好都堆進全域 context。

## 驗證與重啟

Claude Code hooks 安裝或設定變更後：

1. 完整重新啟動 Claude Code。
2. 執行：

```bash
python scripts/verify-install.py
```

3. exit code `0` 才能說 verifier 檢查到的項目通過。

`verify-install.py` 會 live-fire Claude Code hooks，並在本機已安裝時檢查 Cursor / Codex。

## 移除

- 停用單一 hook：從 agent 設定移除該註冊，重啟 agent。
- 完整移除：移除設定註冊，再刪除對應 hook / skill 檔案。
- 如果有安裝前備份，優先用備份協助比對，不盲目整份覆蓋回去。

## 維護 repo 本身

正常流程：

**branch → PR → CI → merge**

不要因為是小改動就直接推 `main`，也不要為了「完整」新增與產品風險無關的治理流程。

### 變更 hook / installer 時

至少跑：

```bash
python hooks/danger-zone-guard/tests/run-tests.py
python hooks/test-gate-guard/tests/run-tests.py
python hooks/tests/run-encoding-tests.py
python -m unittest discover -s tests -p "test_*.py"
```

另外：

- 修改 Python 腳本後確認 syntax / compile。
- 改 Windows 行為要由 Windows CI 或實機驗證；不要用單一平台結果代替跨平台結論。
- 改安裝器時優先測 dry-run、merge、不覆蓋與重跑冪等性。
- 改 hook 行為要補能重現該案例的 regression test。

### 文件分工

- `README.md` / `README.en.md`：產品定位、支援矩陣、快速開始與風險邊界。
- `docs/windows-install*.md`：Windows 安裝與失敗模式。
- `docs/cursor-install*.md`：Cursor `hooks.json` 格式、事件對照，以及 `stop` 只能 follow-up 的限制。
- `docs/antigravity-install*.md`：Antigravity / Gemini 安裝。
- `FORK.md`：fork 差異與上游同步。
- `NOTICE`：attribution。
- `CHANGELOG.md` / `CHANGELOG.en.md`：實際行為、相容性、安裝契約或 release-relevant 變更。

純文字整理或不改產品行為的維護，不必機械式製造 changelog / release。中英文使用者文件若改到同一契約，兩邊要同步。
