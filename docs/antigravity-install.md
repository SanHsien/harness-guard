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

## 驗證安裝

執行以下指令進行安裝自我驗證：

```bash
python scripts/verify-install.py --agent antigravity
```
