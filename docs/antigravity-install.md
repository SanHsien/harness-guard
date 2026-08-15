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

## Antigravity 規則檔整合 (GEMINI.md)

Antigravity 支援階層式規則載入（Global: `~/.gemini/GEMINI.md`，專案層級: 專案根目錄的 `GEMINI.md` 或 `.agents/rules/*.md`）。

1. 參考本 repo 中的 `gemini-md-template/GEMINI.md`。
2. 將其內容合併至你的 `~/.gemini/GEMINI.md` 或當前專案根目錄。
3. 可選的專項規則（如 `gemini-md-template/rules/`）可直接放入 `.agents/rules/` 或 `~/.gemini/config/rules/`。

---

## 信任工作區與免彈窗設定 (Trusted Workspaces & Auto Mode)

若希望 Antigravity 在執行測試與修改檔案時不被頻繁的授權彈窗中斷，可編輯 `~/.gemini/antigravity-cli/settings.json`：

### 1. 信任工作區建議設為家目錄
直接將整個使用者家目錄設為信任路徑，底下的所有現有與未來新增的專案都會自動被涵蓋，無須每次手動增添：

```json
"trustedWorkspaces": [
  "C:\\Users\\<你的使用者名稱>"
]
```

### 2. 開啟全自動執行模式 (Full-Auto)

```json
"agent_features": {
  "auto_run_tests": true,
  "smart_context_retrieval": true,
  "web_search_enabled": true,
  "browser_testing_enabled": true,
  "mcp_enabled": true,
  "auto_approve_commands": true,
  "auto_approve_file_edits": true,
  "skip_permission_prompts": true,
  "auto_execution_mode": "full_auto"
}
```

---

## 驗證安裝

執行以下指令進行安裝自我驗證：

```bash
python scripts/verify-install.py --agent antigravity
```
