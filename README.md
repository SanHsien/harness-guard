[English](README.en.md) | 中文版

# Harness Guard

[![CI](https://github.com/SanHsien/harness-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/SanHsien/harness-guard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**把「請 AI 記得守規則」變成會實際攔截的檢查。**

Harness Guard 是一套給 AI coding agent 使用的 guardrail kit：提供 5 個 hook、11 套 workflow skills、Claude / Gemini 規則檔範本，以及可重現安裝與 live-fire 驗證腳本。Windows 是本 fork 的主要強化方向。

本 repo fork 自 [`agentcrew-academy/harness-starter-kit`](https://github.com/agentcrew-academy/harness-starter-kit)；上游來源、改寫範圍與 attribution 見 [`FORK.md`](FORK.md) 與 [`NOTICE`](NOTICE)。

## 為什麼需要它

提示詞裡的規則會隨長對話被稀釋；hook 則是在 agent 動手前後或準備結束時由程式執行的檢查。

Harness Guard 專注在幾個容易造成實際損失的情境：

- 說「測試過了」卻沒有可對帳的測試紀錄。
- 測試失敗後仍因錯誤的 shell 串接繼續 commit / push。
- 對主分支強推、誤刪根目錄或 `.git`、把 `.env` / 私鑰送出去。
- 收工前沒有通過專案指定的 lint / check。
- 需要明確禁止 emoji 的文件或程式碼工作流。

這些 guardrail 是額外防線，不是 sandbox，也不是形式化安全政策。規則以模式比對與 agent hook 介面實作，仍可能有誤判或漏判。

## 5 個 guardrail hooks

| Hook | 作用 |
|---|---|
| `claim-guard` | 記錄搜尋／測試等工具證據，結束前對帳完成宣稱 |
| `test-gate-guard` | 阻止測試與 `git commit` / `git push` 用 `;` 或換行錯誤串接 |
| `danger-zone-guard` | 攔截特定災難性刪除、保護分支強推與敏感檔外洩 |
| `lint-gate` | turn 結束前執行專案指定檢查；Windows 可用 `.lint-gate.json` 啟用 |
| `no-emoji-guard` | 在指定寫入流程中阻止 emoji；屬偏好型 guardrail，可不安裝 |

完整 hook 介面與平台版本見 [`hooks/`](hooks)。

## 11 套 workflow skills

`explain`、`polite`、`first-principles`、`checkpoint`、`neat-freak`、`review-loop`、`info-diet`、`asd-ste100`、`iso-24495`、`verification-protocol`、`task-orchestrator`。

這些是可選的工作流程，不是五個安全 hook 的必要依賴。內容在 [`skills/`](skills)。

## 支援範圍

| Agent / 環境 | Hooks | Skills / Rules | 安裝方式 |
|---|---|---|---|
| **Claude Code** | 5 個 hook；Windows 會選 Python 版本 | `~/.claude/skills/` + CLAUDE 規則範本 | `install.py` 自動安裝 |
| **OpenAI Codex** | repo 提供 Codex hook 實作與 `codex-hooks-example.json` | skills 可手動整合 | **目前需手動整合；`install.py` 尚未自動註冊 Codex** |
| **Google Antigravity / Gemini** | 本 repo 目前不提供等價 hook 註冊 | skills + `GEMINI.md` 範本 | `install.py --agent antigravity` 可安裝 skills |
| **Cursor / `.agents` 生態** | 無專用 hook installer | `.agents/skills/` 與規則檔可用 | 手動／依 agent 能力整合 |

因此 `--agent all` 目前代表 **Claude Code + Antigravity 的自動化安裝路徑**，不代表 Codex / Cursor 已自動註冊 hook。

## 快速開始

### Claude Code

先預覽，不修改任何設定：

```bash
python scripts/install.py --dry-run --hooks all --skills all
```

確認後正式安裝：

```bash
python scripts/install.py --hooks all --skills all
```

### Google Antigravity / Gemini skills

```bash
python scripts/install.py --dry-run --agent antigravity --skills all
python scripts/install.py --agent antigravity --skills all
```

### 自動化支援的兩個環境一起處理

```bash
python scripts/install.py --dry-run --agent all --hooks all --skills all
python scripts/install.py --agent all --hooks all --skills all
```

安裝程式會盡量**合併而不是覆蓋**既有設定；Claude Code 正式寫入前會備份 `settings.json`。既有同名 skill 預設不覆蓋，除非明確使用 `--force`。

## 驗證安裝

Claude Code hook 安裝後，重新啟動 agent，再跑：

```bash
python scripts/verify-install.py
```

這支工具不只讀設定檔，而會對已安裝 hook 餵合成 payload，確認它真的執行並產生預期的 allow / block 行為。exit code `0` 才代表它檢查到的項目通過。

它主要驗證 Claude Code hook 與 Antigravity skills 目錄；**目前不是 Codex hook 安裝驗證器**。

## Windows

Windows 原生環境不要直接使用依賴 `jq` 的 shell 版本。安裝器會替 Claude Code 選擇 Python 版本，避免 hook 因 `jq` 缺失或 WSL `bash` 路徑而 fail-open。

詳細說明見 [`docs/windows-install.md`](docs/windows-install.md)。Antigravity / Gemini 見 [`docs/antigravity-install.md`](docs/antigravity-install.md)。

## 安裝前的安全原則

這個 repo 的程式會修改 agent 設定，且 hook 會攔截後續操作。安裝任何網路下載的 guardrail 前，都應先閱讀腳本或要求 agent 解釋它會：

1. 複製哪些檔案。
2. 修改哪些設定。
3. 在什麼事件阻擋操作。
4. 如何停用與移除。

不需要全裝。先裝真正對你的風險有價值的 guardrail，比把所有規則堆進 agent 更好。

## 給不熟終端機的使用者

可以把這個 repo 網址交給 AI coding agent，請它先閱讀 [`AGENTS.md`](AGENTS.md)，用白話解釋要改哪些檔案，先執行 dry-run，再逐項安裝。不要要求 agent 略過預覽與驗證。

## 開發與驗證

本 repo 的 CI 會在 Linux 與 Windows 執行核心 Python syntax / regression checks、安裝器 dry-run 契約測試，以及既有 hook 測試。

主要回歸測試：

```bash
python hooks/danger-zone-guard/tests/run-tests.py
python hooks/test-gate-guard/tests/run-tests.py
python hooks/tests/run-encoding-tests.py
python -m unittest discover -s tests -p "test_*.py"
```

維護與安裝規則見 [`AGENTS.md`](AGENTS.md)；版本沿革見 [`CHANGELOG.md`](CHANGELOG.md)。

## 授權

MIT License，見 [`LICENSE`](LICENSE)。原作者、fork 來源與改寫自其他作品的 attribution 見 [`NOTICE`](NOTICE)。
