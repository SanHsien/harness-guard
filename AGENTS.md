# AGENTS.md

給 Claude Code、OpenAI Codex、Google Antigravity (AGY)、Cursor 與其他 AI coding agent 在這個 repo 工作時的指引，**單一真相源**。
Claude Code 專屬補充見 [`CLAUDE.md`](CLAUDE.md)（薄補丁，衝突時以本檔為準）。

如果你正在讀這個檔案，通常是有人把這個 repo 丟給你，要你幫他裝起來。

---

## 先搞清楚你在跟誰講話

**預設對方不會寫程式。** 他很可能只是貼了一個網址說「幫我裝」。他不知道什麼是 hook、什麼是 JSON、什麼是環境變數，也不需要知道。

所以：

- 不要丟術語。非用不可就先用白話解釋一次。
- 不要叫他自己去改設定檔。你改，改完告訴他你改了什麼。
- 不要一口氣裝四五個東西再一次回報。裝一個、講一句「這個裝好了，它會做什麼」，再問要不要繼續。
- 他說「你覺得好就好」「你決定」，那就決定。不要再追問細節，他已經把決定權給你了。

如果對方明顯是工程師（用了技術詞彙、問實作問題），切回正常的技術對話，上面這些都不適用。

---

## 動手前先問三件事

三個一起問，不要一次問一個：

1. **你平常用電腦做什麼？** 寫程式、寫東西做筆記、還是兩者都有。這決定要裝哪些。
2. **有沒有遇過 AI 說「做好了」但其實沒做，或不小心跑了危險指令？** 有的話，claim-guard 與 danger-zone-guard 是他最需要的。
3. **介不介意 AI 在文件裡放表情符號？** 不介意就跳過 no-emoji-guard，免得之後煩他。

---

## 安裝前的環境判定

**第一件事是判斷作業系統與目標 Agent。這決定了要裝哪一版，判斷錯會裝出一個什麼都不擋的空殼。**

### Windows
走 `windows/` 版（Python 實作），並先讀 [`docs/windows-install.md`](docs/windows-install.md)。

- **不要裝 shell 版**：三支 shell hook 都用 `jq` 解析輸入，Windows 原生環境沒有 `jq`，而在沒有 `jq` 時是 `exit 0`——那代表「放行」。
- **hook 指令絕對不要裸寫 `bash`**：Windows 的 `bash` 通常是 `C:\Windows\System32\bash.exe`（WSL），路徑不存在會無聲失敗。

### macOS / Linux
走 `claude-code/` 或 `codex/` 版。Shell 版 hook 需要 `jq`（`which jq`）。

---

## 安裝步驟

### 優先走這條：一行指令重現

```bash
# 預覽安裝計畫
python scripts/install.py --dry-run --agent all --hooks all --skills all

# 正式安裝（自動判別系統與 Agent，合併設定）
python scripts/install.py --agent all --hooks all --skills all
```

### 各 Agent 技能與設定目錄對照

| Agent | 設定/註冊位置 | Skills 目錄 | 說明 |
|---|---|---|---|
| **Claude Code** | `~/.claude/settings.json` 的 `hooks` | `~/.claude/skills/` | 重啟 Claude Code 生效 |
| **OpenAI Codex** | `~/.codex/hooks.json` | `~/.codex/skills/` | `config.toml` 需 `hooks = true` |
| **Google Antigravity** | `~/.gemini/GEMINI.md` 或專案根目錄 | `~/.gemini/config/skills/` | 支援漸進式自動載入 |
| **Cursor** | `.cursorrules` 或 `AGENTS.md` | `.agents/skills/` | 專案根目錄標準 |

---

## 五個攔截工具 (Hooks)

1. **claim-guard**：抓嘴上說測試通過或找不到檔案、實際零紀錄的宣稱。兩支腳本必須一起裝。
2. **no-emoji-guard**：照 Unicode 官方規範過濾文件與程式碼中的 Emoji 裝飾符號。
3. **lint-gate**：收工前強制執行自訂檢查。Windows 版支援專案 `.lint-gate.json` 動態啟用。
4. **test-gate-guard**：擋掉單條指令用 `;` 串接測試與 commit 的紅燈出貨行為。
5. **danger-zone-guard**（本 fork 新增）：攔截根目錄/家目錄刪除、刪除 `.git`、保護分支強推與憑證外洩。

---

## 十一套工作流程 (Skills)

1. **explain**：白話重述，無術語。
2. **polite**：專業修辭與溫暖商務語氣。
3. **first-principles**：第一性原理思考與未知盤點。
4. **checkpoint**：收工日誌與精確提交。
5. **neat-freak**：事實對帳引擎。
6. **review-loop**：長文件段落防丟失與網頁審閱。
7. **info-diet**：本地注意力與瀏覽資訊結構分析。
8. **asd-ste100**：Simplified Technical English 改寫。
9. **iso-24495**：ISO 24495-1 淺白語言改寫。
10. **verification-protocol**（本 fork 新增）：修改即驗證與零偽修正作業協議。
11. **task-orchestrator**（本 fork 新增）：大型任務拆解與 Context 隔離。

---

## 驗證：不准無證據宣稱裝好了

安裝或變更後，一律執行：

```bash
python scripts/verify-install.py
```

exit code 0 才算真正裝好且有效保護。
