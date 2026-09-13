> [English](cursor-install.en.md) | 中文版

# 在 Cursor 上安裝

Cursor 的 hook 契約與 Claude Code 不同。把 Claude Code 的 `settings.json` 區塊整段貼進 Cursor **不會動**。這頁只講差異；通用安裝步驟仍以 [`../AGENTS.md`](../AGENTS.md) 與 `scripts/install.py` 為準。

## 為什麼不能共用 Claude Code 的設定檔

| | Claude Code | Cursor |
|---|---|---|
| 設定檔 | `~/.claude/settings.json` 的 nested `hooks[].hooks[]` | 扁平的 `~/.cursor/hooks.json`，頂層要有 `"version": 1` |
| 擋 shell | `PreToolUse` + matcher `Bash`，`exit 2` | `beforeShellExecution`，stdout `{"permission":"deny"}`（`exit 2` 也可） |
| 擋寫入 | `PreToolUse` + matcher `Write\|Edit\|MultiEdit` | `preToolUse` + matcher `Write` |
| 回合結束 | `Stop` 可以 `{"decision":"block"}` | `stop` **不能否決**，只能 `followup_message` |
| 使用者層 hook 的 cwd | 通常是專案目錄 | `~/.cursor/` |

Cursor 也可以載入 Claude Code 的 third-party hooks，但那要在設定裡另外打開，而且 payload 形狀仍可能是 Cursor 的。本安裝器寫的是 Cursor 原生格式，不依賴那個開關。

## 安裝

```bash
python scripts/install.py --dry-run --agent cursor --hooks all --skills all
python scripts/install.py --agent cursor --hooks all --skills all
```

安裝器會：

1. 把 Python hook 平放進 `~/.cursor/hooks/`。
2. **合併**進 `~/.cursor/hooks.json`（先備份），重跑不重複註冊。
3. 把 skills 複製到 `~/.cursor/skills/`。若本機已經有 `~/.agents/skills/`，也合併進去；既有同名資料夾不覆蓋。

Windows 上的 `command` 是 `python "C:\Users\<你>\.cursor\hooks\....py"`，不用 shebang、不用相對路徑。相對路徑在使用者層 hook 的 cwd 下也許找得到檔，但 Windows 不會靠 shebang 選 interpreter。

## 事件對照

| Guard | Cursor 事件 | 擋得下來嗎 |
|---|---|---|
| test-gate-guard | `beforeShellExecution` | 可以。頂層 `command` |
| danger-zone-guard | `beforeShellExecution` | 可以 |
| no-emoji-guard | `preToolUse`（matcher `Write`） | 可以，回 `permission: deny` |
| claim-ledger-tracker | `postToolUse` | 只記帳，不擋 |
| claim-evidence-guard | `stop` | **不能 veto**。有完成宣稱但沒證據時送 `followup_message` |
| lint-gate | `stop` | 同上；專案目錄來自 payload `cwd` / `workspace_roots`，不是 `~/.cursor` |

沒有 `last_assistant_message` 時，claim-evidence-guard 維持 fail-open。這不是 Cursor 特有的寬鬆，是這支 hook 一直以來的契約：解析不出訊息就不要攔。

## 驗證

```bash
python scripts/verify-install.py --agent cursor
```

它會對已複製的腳本餵 Cursor 形狀的 payload。設定檔看起來對、但 live-fire 沒擋下來，仍算沒裝好。

改完 `hooks.json` 後，Cursor 通常會自動重載。若 Hooks 輸出頻道沒看到新 hook，重開視窗。
