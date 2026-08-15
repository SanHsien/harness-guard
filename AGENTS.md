# AGENTS.md

給 Codex 與其他 AI coding agent 在這個 repo 工作時的指引，**單一真相源**。
Claude Code 專屬補充見 [`CLAUDE.md`](CLAUDE.md)（薄補丁，衝突時以本檔為準）。

如果你正在讀這個檔案，通常是有人把這個 repo 丟給你，要你幫他裝起來。

---

## 先搞清楚你在跟誰講話

**預設對方不會寫程式。** 他很可能只是貼了一個網址說「幫我裝」。他不知道什麼是
hook、什麼是 JSON、什麼是環境變數，也不需要知道。

所以：

- 不要丟術語。非用不可就先用白話解釋一次。
- 不要叫他自己去改設定檔。你改，改完告訴他你改了什麼。
- 不要一口氣裝四五個東西再一次回報。裝一個、講一句「這個裝好了，它會做什麼」，
  再問要不要繼續。
- 他說「你覺得好就好」「你決定」，那就決定。不要再追問細節，他已經把決定權給你了。

如果對方明顯是工程師（用了技術詞彙、問實作問題），切回正常的技術對話，上面這些都不適用。

---

## 動手前先問三件事

三個一起問，不要一次問一個：

1. **你平常用電腦做什麼？** 寫程式、寫東西做筆記、還是兩者都有。這決定要裝哪些。
2. **有沒有遇過 AI 說「做好了」但其實沒做？** 有的話，claim-guard 是他最需要的。
3. **介不介意 AI 在文件裡放表情符號？** 不介意就跳過 no-emoji-guard，免得之後煩他。

---

## 安裝前的環境判定

**第一件事是判斷作業系統。這決定了要裝哪一版，判斷錯會裝出一個什麼都不擋的空殼。**

### Windows

走 `windows/` 版，並先讀 [`docs/windows-install.md`](docs/windows-install.md)。
三件事必須知道：

- **不要裝 shell 版。** 三支 shell hook 都用 `jq` 解析輸入，Windows 原生環境沒有
  `jq`，而它們在沒有 `jq` 時是 `exit 0`——那代表「放行」。註冊成功、設定檔看起來
  對、什麼都不擋。
- **hook 指令絕對不要裸寫 `bash`。** Windows 的 `bash` 通常是
  `C:\Windows\System32\bash.exe`，那是 WSL：家目錄不同、檔案系統不同，
  `~/.claude/hooks/x.sh` 在那裡不存在，hook 從頭到尾沒跑過。要用 Git Bash 就寫完整
  路徑 `"C:\Program Files\Git\bin\bash.exe"`。
- **沒有 `chmod`、沒有 `brew`。** 這兩個步驟直接跳過，不要照 macOS 的說明念給對方聽。

Windows 版是 Python 寫的，除了 Python 本身沒有任何相依。先確認：

```powershell
python --version
```

### macOS / Linux

走 `claude-code/` 或 `codex/` 版。三支 hook 都需要 `jq`：

```bash
which jq
```

沒有的話，macOS 是 `brew install jq`。如果連 `brew` 都沒有，不要直接叫他去裝
Homebrew——那對不會寫程式的人是個大工程。告訴他有這件事，問他要不要現在處理，
或者先只裝不需要 `jq` 的部分（skills 都不需要）。

---

## 安裝步驟

### 優先走這條：一行指令

對方有 Python、而且你在 Claude Code 環境（或目標是 Claude Code）的話，先用這支：

```bash
python scripts/install.py --dry-run --hooks all --skills all   # 先看會動到什麼
python scripts/install.py --hooks all --skills all             # 真的裝
```

它自動判平台挑對版本、**合併**進既有 `settings.json`（不覆蓋）、先備份、原子寫入、
寫完讀回驗證 JSON 仍合法，重跑不會重複註冊，既有 skill 資料夾不覆蓋。

**先跑 `--dry-run` 給對方看再問要不要執行。** 這是在改他的設定檔，讓他看得到你要動什麼。

不適用這支腳本的情況（目標是 Codex、或對方環境沒有 Python），照下面的手動步驟走。

### hooks（四個攔截工具）

1. 把腳本檔複製到該 agent 的 hook 目錄，**平放在最上層，不要保留這個 repo 的資料夾層次**。
   目錄對照：

   | agent | hook 目錄 | 註冊在 | 範本 |
   |---|---|---|---|
   | Claude Code | `~/.claude/hooks/` | `~/.claude/settings.json` 的 `hooks` 區塊 | `settings-example.json`；Windows 用 `settings-example.windows.json` |
   | Codex | `~/.codex/hooks/` | `~/.codex/hooks.json`，且 `~/.codex/config.toml` 要有 `hooks = true` | `codex-hooks-example.json` |

2. macOS / Linux 要 `chmod +x`；Windows 不用。
3. 依上表把需要的區塊**合併**進設定檔。

**註冊是最常出錯的一步，盯緊兩件事：**

- 對方的設定檔幾乎一定已經有東西了。**用合併，不要覆蓋。** 覆蓋會弄壞他既有的設定。
- 動手前先備份，改完驗證 JSON 還是合法的：
  `python -c "import json;json.load(open('...',encoding='utf-8'))"`。
  JSON 壞掉 Claude Code 會起不來，對不會寫程式的人是災難。

claim-guard 的兩支腳本必須**一起**裝。只裝一支會無聲失效、不會報錯——使用者會以為
自己被保護著，其實沒有。

test-gate-guard 是純 Python，三個平台通用，註冊在 PreToolUse 的 `Bash` matcher。
它自己附回歸測試，裝之前可以先跑給對方看：

```bash
python hooks/test-gate-guard/tests/run-tests.py
```

lint-gate 需要一個檢查指令才有意義。對方講不出要檢查什麼就先跳過，不要硬塞一個
`npm run lint` 給一個不寫程式的人。

### skills（九套工作流程）

複製到該 agent 讀得到的技能目錄（Claude Code 是 `~/.claude/skills/`），
各自保留自己的資料夾。不需要註冊，放進去就能用。

`skills/` 底下都是純文字指引，不綁平台。兩個例外要處理：

- **review-loop** 附了一支 Python 腳本跟一個 HTML 範本，整包複製，不要只拿 SKILL.md。
  裝完把 SKILL.md「commands」段落裡的路徑改成實際安裝位置，然後跑
  `bash skills/review-loop/examples/regression/run-test.sh` 給對方看
  （應該是 10 passed, 0 failed），邊跑邊解釋它在測什麼。對方沒有「反覆修長文件」
  的需求就可以跳過。
- **checkpoint 與 neat-freak** 要照對方實際的檔案擺法調整過才會準。裝完問他筆記跟
  專案平常放哪，幫他改 `skills/neat-freak/references/sync-matrix.md` 裡的對照表。
  他當下答不出來就先跳過——這兩套沒調整不會壞，只是對帳結果不準。

explain 與 polite 開箱即用，不用調。

skill 裡提到的「subagent」在各家 agent 有對應概念，只是名字不同，照自己的慣例對應即可。

### claude-md-template（規則檔範本）

這個是**合併**，不是複製，跟前兩類不一樣：

1. 先看對方有沒有既有的規則檔（Claude Code 是 `~/.claude/CLAUDE.md`，其他 agent 常見
   是 `~/.codex/AGENTS.md` 或等價位置）。**有的話絕對不要覆蓋**——一段一段讀過去問
   「這條適用於你嗎」，只把適用的合併進去，每次都確認他既有的檔案是不是已經講過同樣的事
   （一條規則只該存在一次，兩份會互相稀釋）。沒有的話才整份複製過去。
2. 範本裡有空格（＿＿＿）要當場跟他一起填：他是誰、做什麼的、要用什麼語言回覆、時區。
   留空就等於沒裝。
3. 「背景」那段多問一句：「有沒有什麼你的判斷標準或偏好，是 AI 猜不到、但猜錯你會很困擾的？」
   把他的回答寫成一兩行加進去。想不出來就先留白，之後遇到再補。
4. `rules/` 裡三個檔案是可選的，一個一個問。要的複製到對應的 rules 目錄；
   同名檔案已存在就合併不覆蓋，同第 1 點。
5. 提醒他：這份範本是靠**減法**維護的。之後每次想加一行，先問「沒有這一行，AI 會不會犯錯？」
   不會就不要加。

---

## 裝完必須說的一句話

**「你要把 Claude Code（或你在用的 agent）整個關掉重開，剛才裝的東西才會生效。」**

這些攔截工具只在啟動時載入。沒重啟就等於沒裝，而使用者會以為裝好了。這句話要講清楚，
要確定他聽進去了。

---

## 驗證：不准無證據宣稱裝好了

這整包東西的主題就是「沒有證據的完成宣稱不算數」。你自己更不能是破例的那個。

Claude Code 環境直接跑：

```bash
python scripts/verify-install.py
```

它不是讀設定檔然後宣布沒問題，而是餵合成 payload 給每一個已安裝的 hook、實際執行、
再檢查回應：claim-guard 在帳本空的時候有沒有擋下「測試通過」、帳本有紀錄後有沒有放行；
lint-gate 失敗時有沒有擋、第二次有沒有放行（避免無限迴圈）；test-gate-guard 有沒有擋掉
`pytest ; git push` 而放行 `pytest && git push`。同時會標出設定裡的裸 `bash` 與缺少的 `jq`。

exit code 0 才算裝好。其他 agent 沒有對應腳本的話，至少手動觸發一次，親眼看它擋下來。

**不要因為沒報錯就當作它在運作**——那正是這三個工具存在的理由。

---

## 使用者反悔的話

有人裝完覺得一直被擋很煩，這很正常。移除方式：

- 只想暫時停用其中一個：從設定檔刪掉那一段、重啟即可，腳本檔可以留著。
- 全部移除：刪掉設定檔裡對應的區塊，再刪掉 hook 目錄與 skills 目錄下的對應檔案。

不要因為他想移除就試圖說服他留下。那是他的電腦。

---

## 各平台介面差異

事件名兩邊一樣（`PreToolUse`、`PostToolUse`、`Stop`、`SessionStart`、`UserPromptSubmit`），
`matcher` + `hooks` 結構也一樣。真正的差別是這五點，想自己移植別的 hook 就照這張表：

| | Claude Code | Codex |
|---|---|---|
| 設定放哪 | `settings.json` 的 `hooks` 區塊 | 獨立的 `~/.codex/hooks.json`，且 `config.toml` 要 `hooks = true` |
| 這一輪的識別碼 | `session_id` | **`turn_id`**（保險寫法是 `.turn_id // .session_id` 兩個都試） |
| matcher 裡的工具名 | `Write`/`Edit`/`MultiEdit`/`Bash`/`WebFetch` | 改檔案是 `apply_patch`、跑指令是 `exec`/`shell`/`exec_command`、抓網頁是 `web_fetch` |
| 專案目錄 | 環境變數 `CLAUDE_PROJECT_DIR` | 沒有，改從 payload 讀 `cwd` |
| 放行時要輸出什麼 | 安靜結束即可 | **要印 `{}`**，什麼都不印會被當成異常 |
| 怎麼表達攔截 | `exit 2` + 訊息寫 stderr | 印 `{"decision":"block","reason":"..."}` |
| 信任機制 | 無 | hook 要先被信任才會執行，第一次啟用需確認 |

Codex 另有 `PostCompact`；Claude Code 另有 `PreCompact`、`SessionEnd`、`Notification`。
兩邊各有對方沒有的事件，接之前先確認你要的那個真的存在。

`stop_hook_active`、`last_assistant_message`、`tool_name`、`tool_input` 兩邊欄位名相同，
可以直接沿用。

`hooks/*/codex/` 底下已經是適配好的 Codex 版，**直接複製進 `~/.codex/hooks/` 即可，
不需要自己移植。**

---

## 對你自己的要求

- **沒驗證過就不要說裝好了。** 複製完確認檔案真的在那裡；改完 JSON 確認它還是合法的。
- **每支腳本你要自己先讀過再複製。** 這些是會攔截工具呼叫的程式，你正在安裝的東西會影響
  這個人之後所有的工作。
- 出錯就直說。中途卡住就明確講卡在哪，不要跳過去繼續裝下一個。
- 有東西沒裝成、有東西你改寫過，講清楚。只有實際測過的才能說它能用。

---

## 維護這個 repo 本身

- 這是一份 fork，改動範圍與上游同步方式見 [`FORK.md`](FORK.md)。
- 文件語言：`README.md`／`AGENTS.md`／`CLAUDE.md`／`docs/*.md` 以繁體中文為主，
  英文放 `*.en.md` 鏡像檔。改中文版時記得同步英文版。
- 本檔與 `CLAUDE.md` 的分工：通用規則一律寫在這裡，`CLAUDE.md` 只放 Claude Code 專屬的
  路徑與介面細節，不重複規則。
