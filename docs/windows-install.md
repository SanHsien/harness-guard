> [English](windows-install.en.md) | 中文版

# 在 Windows 上安裝

主 README 的步驟預設是 macOS 或 Linux。在 Windows 上，其中三個步驟不會成功，
而且三個都不會告訴你它失敗了。這頁是 Windows 的走法。

以下每一項都在真實的 Windows 11 機器上實測過，不是從文件推論的。

---

## 哪裡會壞，以及為什麼是無聲的

### 1. 沒有 `jq`

三個 shell hook 都用 `jq` 解析輸入。Windows 原生環境沒有 `jq`，而
`winget install jqlang.jq` 是多數人會跳過的額外步驟。

失敗的方式是最糟的那種。`claim-evidence-guard.sh` 這樣讀輸入：

```bash
SID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null) || exit 0
```

沒有 `jq` 就 exit 0，exit 0 就是「放行」。沒有錯誤、沒有訊息、log 裡什麼都沒有。
hook 註冊了、設定檔看起來對，但它什麼都沒擋。

### 2. 裸寫 `bash` 會叫到 WSL，不是 Git Bash

把 hook 註冊成 `bash ~/.claude/hooks/claim-evidence-guard.sh`，Windows 會照
`PATH` 找 `bash`，而 `C:\Windows\System32\bash.exe` 通常排在最前面——那是 WSL
的啟動器。進到 WSL 裡：

```
$ bash -c 'echo $HOME; ls ~/.claude/hooks/'
/home/<你>
ls: cannot access '/home/<你>/.claude/hooks/': No such file or directory
```

家目錄不同、檔案系統不同。腳本明明在 `C:\Users\<你>\.claude\hooks\`，那個 `~`
指的不是那裡。hook 從頭到尾沒執行過。

Git Bash 本身沒問題，但必須用完整路徑明確指定：
`"C:\Program Files\Git\bin\bash.exe"`。

### 3. `chmod +x`、`which jq`、`brew install jq`

這三個在 Windows 都不適用。沒有執行位元，也沒有 `brew`。

---

## Windows 版

每個 hook 底下多了一個 `windows/` 資料夾，與 `claude-code/`、`codex/` 並列：

```
hooks/claim-guard/windows/claim_ledger_tracker.py
hooks/claim-guard/windows/claim_evidence_guard.py
hooks/lint-gate/windows/lint_gate.py
hooks/no-emoji-guard/claude-code/no-emoji-guard.py   （本來就是 Python，直接可用）
hooks/test-gate-guard/claude-code/test_gate_guard.py （Python，三個平台都能跑）
```

判斷邏輯與 shell 版完全一致——同樣的觸發詞、同樣的 fail-open 規則、同樣的訊息。
換掉的只有底層管線：

| | shell 版 | Windows 版 |
|---|---|---|
| 解析輸入靠 | `jq` | Python 標準函式庫 |
| 執行於 | `bash` | `python` |
| lint-gate 設定方式 | `VAR=value` 前綴（只有 POSIX shell 認得） | `--cmd` / `--fail` 參數，在 cmd、PowerShell、Git Bash 意思都一樣 |
| 額外相依 | `jq` | 無 |

兩版共用同一個帳本目錄（`%USERPROFILE%\.cache\claude-guard-hooks`），互換不需要清理。

---

## 安裝

**1. 確認有 Python。** 在 PowerShell：

```powershell
python --version
```

3.8 以上都可以。如果沒有正常輸出，去 python.org 裝好後重開終端機。

**2. 把 hook 複製進去。** 平放進 `%USERPROFILE%\.claude\hooks\`，
不要保留這個 repo 的資料夾層次：

```powershell
$dst = "$env:USERPROFILE\.claude\hooks"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item hooks\claim-guard\windows\*.py $dst
Copy-Item hooks\lint-gate\windows\lint_gate.py $dst
Copy-Item hooks\no-emoji-guard\claude-code\no-emoji-guard.py $dst
Copy-Item hooks\test-gate-guard\claude-code\test_gate_guard.py $dst
```

沒有 `chmod` 這一步，Windows 不存在這個東西。

**3. 註冊。** 把 [`settings-example.windows.json`](../settings-example.windows.json)
裡需要的區塊合併進 `%USERPROFILE%\.claude\settings.json`。

這一步最常出錯的兩件事：

- 你的 `settings.json` 幾乎一定已經有內容。要**合併**，不要覆蓋。動手前先備份。
- 路徑寫**完整絕對路徑**，不要用 `~`。`~` 會不會展開，取決於最後是哪個 shell
  在執行這條指令——而那正是這頁在講的那個歧義。

**4. 完全關掉 Claude Code 再開。** hook 只在啟動時載入。沒有重啟，剛才做的一切
都還沒生效。

**5. 用證據確認，不要用假設。**

```powershell
python scripts\verify-install.py
```

這支腳本不是讀設定檔然後宣告一切正常。它會餵合成 payload 給每個已安裝的 hook，
真的執行一次，再檢查回應：claim-guard 在帳本空的時候是否擋下「測試通過」、
在帳本有真實測試紀錄後是否放行；lint-gate 檢查失敗時是否擋下、第二次是否放行
（避免無限迴圈）；test-gate-guard 是否擋掉 `pytest ; git push` 而放行
`pytest && git push`。它同時會標出設定裡的裸 `bash` 指令，以及缺少 `jq` 的情況。

exit code 0 代表每個已安裝的元件都答對了。

---

## 如果你堅持要用 shell 版

可以，但有兩個條件：

1. 裝 `jq`：`winget install jqlang.jq`，然後重開終端機。
2. 註冊時用 Git Bash 的完整路徑，絕不裸寫 `bash`：

```json
"command": "\"C:\\Program Files\\Git\\bin\\bash.exe\" \"C:\\Users\\<你>\\.claude\\hooks\\claim-evidence-guard.sh\""
```

裝完跑 `python scripts\verify-install.py` 確認全綠。不管走哪條路，結論一樣：
沒有親眼看它擋下來過的 hook，就是你不知道它到底有沒有裝好的 hook。
