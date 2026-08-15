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

## 裝什麼、各是做什麼的

五個攔截工具與十一套工作流程的說明在 [`README.md`](README.md)，不在這裡重複一遍。
要跟使用者解釋某一支在做什麼，去讀那份。

安裝時只有三件事是這裡才有的：

- **claim-guard 的兩支腳本必須一起裝**，只裝一支會無聲失效。
- **lint-gate 需要一個檢查指令才有意義**，對方講不出要檢查什麼就先跳過（Windows 版可留著
  全域註冊，讓各專案自己丟 `.lint-gate.json` 開啟）。
- **checkpoint 與 neat-freak 要照對方的檔案擺法調過才會準**，當下答不出來就先跳過，
  它們不會壞，只是對帳結果不準。

---

## 沒有安裝腳本可用時的手動步驟

對方沒有 Python，或目標 agent 不是 Claude Code 時走這條：

1. 把腳本檔複製到該 agent 的 hook 目錄，**平放在最上層**，不要保留這個 repo 的資料夾層次。
   （平放是為什麼 hook 之間不可以互相 import 檔案——裝完之後那些相對路徑都不存在了。）
2. macOS / Linux 要 `chmod +x`；Windows 不用。
3. 把設定範本裡需要的區塊**合併**進設定檔。

註冊這一步最常出錯，盯緊兩件事：

- 對方的設定檔幾乎一定已經有東西了。**合併，不要覆蓋**，動手前先備份。
- 改完驗證 JSON 仍合法：`python -c "import json;json.load(open('...',encoding='utf-8'))"`。
  JSON 壞掉 agent 會起不來，對不會寫程式的人是災難。

claim-guard 的兩支腳本必須**一起**裝，只裝一支會無聲失效。
lint-gate 需要一個檢查指令才有意義，對方講不出要檢查什麼就先跳過。

---

## 規則檔範本：合併，不是複製

`claude-md-template/` 與 `gemini-md-template/` 是**合併**進既有規則檔的，跟 hooks 與 skills 不同。

1. 先看對方有沒有既有的規則檔。**有的話絕對不要覆蓋**——一段一段問「這條適用於你嗎」，
   只併適用的，每次都確認他既有的檔案是不是已經講過同樣的事（一條規則只該存在一次，
   兩份會互相稀釋）。沒有才整份複製。
2. 範本裡的空格（＿＿＿）要當場跟他一起填：他是誰、做什麼的、用什麼語言回覆、時區。
   留空等於沒裝。
3. 多問一句：「有沒有什麼你的判斷標準或偏好，是 AI 猜不到、但猜錯你會很困擾的？」
   把回答寫成一兩行加進去。想不出來就先留白。
4. 提醒他：規則檔靠**減法**維護。之後每次想加一行，先問「沒有這一行，AI 會不會犯錯？」

---

## 裝完必須說的一句話

**「你要把 agent 整個關掉重開，剛才裝的東西才會生效。」**

攔截工具只在啟動時載入。沒重啟就等於沒裝，而使用者會以為裝好了。這句話要講清楚，
要確定他聽進去了。

---

## 驗證：不准無證據宣稱裝好了

安裝或變更後，一律執行：

```bash
python scripts/verify-install.py
```

exit code 0 才算真正裝好且有效保護。

**不要因為沒報錯就當作它在運作**——那正是這些工具存在的理由。其他 agent 沒有對應腳本的話，
至少手動觸發一次，親眼看它擋下來。

對你自己的三個要求：

- 沒驗證過就不要說裝好了。複製完確認檔案真的在那裡，改完 JSON 確認它還是合法的。
- 每支腳本你要自己先讀過再複製。你正在安裝的東西會影響這個人之後所有的工作。
- 出錯就直說，卡住就講清楚卡在哪，不要跳過去繼續裝下一個。

---

## 使用者反悔的話

有人裝完覺得一直被擋很煩，這很正常。移除方式：

- 只想停用其中一個：從設定檔刪掉那一段、重啟即可，腳本檔可以留著。
- 全部移除：刪掉設定檔裡對應的區塊，再刪掉 hook 與 skills 目錄下的對應檔案。

不要因為他想移除就試圖說服他留下。那是他的電腦。

---

## 維護這個 repo 本身

- 這是一份 fork，改動範圍與上游同步方式見 [`FORK.md`](FORK.md)。
- 文件語言：`README.md`／`AGENTS.md`／`CLAUDE.md`／`docs/*.md` 以繁體中文為主，
  英文放 `*.en.md` 鏡像檔。改中文版時同步英文版。
- 本檔與 `CLAUDE.md` 的分工：通用規則一律寫在這裡，`CLAUDE.md` 只放 Claude Code 專屬的
  路徑與介面細節，不重複規則。
- 改完 hook 一定要跑對應的回歸測試（`hooks/*/tests/run-tests.py`）與
  `hooks/tests/run-encoding-tests.py`，並在**目標作業系統上**跑一次 `scripts/verify-install.py`。
  只在一個平台上綠燈不算數。
- 有使用者看得到的改動就寫進 [`CHANGELOG.md`](CHANGELOG.md)（與 `CHANGELOG.en.md`）。
  README 只講「這是什麼、怎麼用」，版本沿革一律進 CHANGELOG。
- **hook 之間不可以互相 import。** 安裝是平放的，裝完之後 repo 的資料夾結構不存在，
  靠相對路徑 import 的 hook 一定壞。要共用邏輯就複製一份。
