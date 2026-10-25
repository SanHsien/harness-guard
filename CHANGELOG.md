> [English](CHANGELOG.en.md) | 中文版

# 變更紀錄

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，新的在上面。
`fork` 標記的是本 fork 相對於
[上游](https://github.com/agentcrew-academy/harness-starter-kit) 的改動。

---

## 2026-10-25

### 修正

- **上游檢查器 `check_upstream_updates.py`：沒查成的情況一律 exit 2（`fork`）。** 以前沒裝 `gh`、`gh` 輸出形狀不對、
  寫不出報告、主控台編碼或 stdout 壞掉都會變成 traceback + exit 1，`--strict` 呼叫端讀成「有未審 commit」。
  現在都寫出「Check failed／Not checked」並 exit 2；上游改寫歷史時明確報 rewritten，shallow clone 則報 shallow，
  不再列出一段看似正常的新 commit。
  載入 baseline 時也驗證：`reviewed_through` 必須是完整 SHA、PR／issue 水位必須是非負整數、`repo` 與 `branch`
  不得以 `-` 開頭（否則會被 git 當成 `--upload-pack=...` 之類的選項）；本機上游路徑可含空白
  （例如 `C:\Program Files\up`），分支名不行。報告以 `errors="replace"` 寫入，標題裡有孤立 surrogate 也不會沒有報告檔。
- **Windows：Claude Code 的 PowerShell 工具完全繞過 `danger-zone-guard` 與 `test-gate-guard`（`fork`）。**
  兩者只登記 `Bash` matcher，腳本也只認 `Bash` 等工具名，所以經 PowerShell 工具跑的 `git push --force`、
  `pytest ; git push` 一律放行——而 `;` 正是 PowerShell 常用的分隔符。matcher 改為 `Bash|PowerShell`，
  兩支腳本把 `PowerShell` 當 shell 工具；重跑 `install.py` 會把舊 matcher 的登記搬過去。
- **重跑安裝器不會更新 matcher 已改的登記（`fork`）。** 同一支腳本、同一條命令只要已在任何 matcher
  群組裡，安裝器就回報「already registered」；hook 需要看到的工具清單後來變寬（例如
  `anti-doom-loop-guard` 在 c38bfd7 加入編輯工具，讓改檔能重置計數），舊安裝重跑也拿不到，計數照樣
  不重置。現在 Claude Code、Codex、Cursor、Antigravity 都只把「同命令且同 matcher」算已登記；舊 matcher
  下的同腳本登記會被移除並改登到現行 matcher（輸出 `removed N outdated registration(s)`），同群組裡使用者自己的 hook 不動。
- **claim-guard：測試跑完再改檔，「測試通過」仍被當成有證據（移植自上游 e9a4734）。** 記帳端現在
  也記改檔（Claude `Write|Edit|MultiEdit|NotebookEdit`、Codex `apply_patch`、Cursor `Write|Delete`、
  Antigravity `write_to_file|replace_file_content|multi_replace_file_content`），查驗端在「最後一次改檔晚於
  最後一次驗證」時擋一次並列出兩者；第二次（`stop_hook_active`）照舊放行。shell 版與 Python 版都有。
- **claim-guard：提到觸發詞也被當成宣稱（移植自上游 e9a4734）。** 「」與反引號 `` ` `` 內的文字先去掉再比對，
  寫「我把 `tests pass` 加進觸發清單」不再被擋。shell 版用 `jq` 的 Unicode regex，不依賴 locale。

### 新增

- **claim-guard 記帳端多記幾種證據（移植自上游 7b0df03／e9a4734）**：`WebSearch`／`WebFetch`（Codex 的
  `web_fetch`）算搜尋；`mcp__claude-in-chrome__*` 與 `playwright test`／`agent-browser` 算驗證；Windows 上
  Claude Code 的 `PowerShell` 工具與 `Bash` 同樣記帳。安裝器的 tracker matcher 隨之加寬（Claude、Codex、
  Antigravity），重跑 `install.py` 會把舊 matcher 的登記搬過去；`verify-install.py` 會檢查 matcher 涵蓋改檔工具。

## 2026-10-23

### 修正

- **Antigravity：所有 `run_command` 都被擋下（`fork`）。** 症狀是 Antigravity 回報
  `tool call denied by pre-tool hook: `，冒號後面沒有原因，連 `python -c "print('hello')"` 也被擋。
  原因：官方規定 `PreToolUse` 的輸出 `decision` 為**必填**，而 `danger-zone-guard`、`test-gate-guard`、
  `no-emoji-guard`、`anti-doom-loop-guard` 放行時回的是空的 `{}`，被當成否決。解法：放行改回
  `{"decision":"ask"}`，交給 Antigravity 原本的權限流程（會尊重「一律允許」設定）；不回 `allow`，
  那會自動核准並跳過授權彈窗。`PostToolUse` 與放行的 `Stop` 仍回 `{}`（官方規定）。已裝過的人重跑
  `python scripts/install.py --agent antigravity --hooks <名稱>` 即可換成新版；`verify-install.py`
  現在會檢查放行輸出是 ask。

### 新增

- **`anti-doom-loop-guard` 擴及 Codex、Cursor、Antigravity，並可由安裝器安裝（`fork`）。**
  同一個 Bash／Read 呼叫連續 3 次且中間沒有其他工具呼叫就擋下（舊行為不變）。一支檔案內含共用核心
  （簽章、狀態、門檻、稽核紀錄）與四個薄 adapter，因為 hook 平放安裝、不能互相 import：
  Codex 回 `{"decision":"block"}`（需 `--agent codex`，payload 與 Claude 相似）、Cursor 走
  `preToolUse`（`Shell|Read|Write|Delete`）回 `{"permission":"deny"}`、Antigravity 走 `PreToolUse`
  （`toolCall`）回 `{"decision":"deny"}`。Cursor 不用 `beforeReadFile`：它沒有 offset／limit，分頁讀大檔會被誤判。
  Cursor／Antigravity 的 Read 以整組工具參數當簽章，不依賴猜測的欄位名。
- **`install.py --agent <claude|codex|cursor|antigravity> --hooks anti-doom-loop-guard` 只安裝這個 hook。**
  Claude 端把既有手動安裝（同檔名、同 matcher 的 `PreToolUse` 登記，引號／斜線／大小寫不同也算）
  視為已存在，不重複加入。Antigravity 首度支援 hook：合併進 `~/.gemini/config/hooks.json`
  （頂層以 hook 名稱為 key），命令不加引號、路徑含空白時拒絕安裝；沒有 `--hooks` 時 Antigravity
  仍只裝 skills。`--dry-run` 現在會列出會複製與合併的檔案。
- **`verify-install.py` 對四個 agent 都 live-fire `anti-doom-loop-guard`**：改檔夾在中間不擋、連續
  3 次相同指令依該 agent 的格式擋；並檢查 Antigravity 命令無引號與 Codex 的 `--agent codex`。
- **Antigravity 的 5 個守衛 hook（`fork`）：`danger-zone-guard`、`test-gate-guard`、`no-emoji-guard`、
  `claim-guard`、`lint-gate`。** 之前 Antigravity 的 `hooks.json` 用 Claude Code 版面放這些 hook，
  被整份拒絕、一個都沒跑過。現在各自是 `hooks.json` 裡的具名 hook：`PreToolUse`（`run_command`；
  `no-emoji-guard` 是 `write_to_file|replace_file_content|multi_replace_file_content`）否決回
  `{"decision":"deny"}`，`claim-guard` 的記帳端走 `PostToolUse`（`run_command|grep_search|find_by_name|list_dir`，
  失敗的工具呼叫不記），查驗端與 `lint-gate` 走 `Stop`（**扁平** handler 清單，沒有 matcher）擋下結束回
  `{"decision":"continue"}`，放行一律 `{}`。同一支腳本，用 `toolCall` / `conversationId` 辨認 Antigravity，
  Claude／Codex／Cursor 行為不變。`Stop` 沒有 `stop_hook_active`，所以同一則訊息／同一份失敗只擋一次。
  **限制：** `Stop` payload 沒有助理訊息，`claim-guard` 查驗端改讀 `transcriptPath`，檔案行格式官方文件沒寫，
  照 `run-workflow` 文件的 step 形狀讀、讀不到就放行；herdr 的 hook 不在範圍。細節見
  `docs/antigravity-install.md`。
- **`install.py --agent antigravity --hooks <名稱>[,<名稱>...]` 可安裝這 6 個 hook 的任意組合**
  （`--hooks all` 即全部）：具名登記、先備份、寫完讀回、重跑不重複、已存在的同名登記視為已安裝。
  `verify-install.py --agent antigravity` 對每個已登記的 hook 檢查版面並 live-fire 一次放行、一次攔截。
  新增 `hooks/tests/run-antigravity-tests.py`（納入 CI）。

### 變更

- `--hooks all` 現在也會安裝 `anti-doom-loop-guard`（預設清單不變）。
- 安裝器寫入 JSON 設定後會真的讀回比對，再印出「re-read and valid」（先前只印不讀）。
- **Antigravity：`hooks.json` 頂層有 Claude Code 版面的 `hooks` 區塊、或有 entry 的形狀 Antigravity 會拒絕（例如 `Stop`
  包成 matcher 分組）時，安裝器改為拒絕寫入**（印 `REFUSED` 與原因，不複製、不備份）。先前是提醒後照寫，
  結果是整份檔案仍被 Antigravity 拒絕、hook 從不執行卻顯示安裝成功。

### 修正

- 狀態檔名含 session id，現在會過濾路徑字元；先前含 `/` 的 id 會讓狀態寫入無聲失敗而失去防護。
- **`danger-zone-guard`、`test-gate-guard`、`no-emoji-guard` 對 Antigravity 放行時改回 `{}`**，不再回
  `{"decision":"allow"}`：後者在 Antigravity 是「自動核准這次呼叫」，會跳過使用者仍想要的授權彈窗。

## 2026-09-20

### 修正

- **完成宣稱的機器證據改為 fail-closed（`fork`）。** opt-in repo 的 Full summary 現在必須是
  schema v1、`full` profile、綁定目前 Git HEAD，且所有 gates 都是 boolean true；第二次 Stop
  不再繞過這項檢查。新增回歸測試並納入 CI。
- **危險區 guard 會攔截無界限 Bash／PowerShell 迴圈（`fork`）。** 明確有界限的特殊情況可用
  `# bounded-loop-ok: <理由>` 說明；引號內範例不會被誤判。
- **Windows 安裝驗證可正確解析未加引號的絕對 Python hook 路徑（`fork`）。** 不再把含空白的
  interpreter／script command 誤判成 hook 檔案缺失。

## 2026-08-24

### 修正

- **Codex claim tracker 漏接新版 shell 工具別名（`fork`）。** 新版 Codex rollout
  會把命令記為 `exec_command` 或 `shell_command`；舊 tracker 只接受 `exec`、`shell` 與
  `Bash`，而 POSIX 版本更只接受 `Bash`，因此命令確實執行後仍可能沒有 claim ledger。
  Windows／POSIX tracker 與安裝器 hook matcher 現在同步接受兩個別名及 `cmd` payload，
  `scripts/verify-install.py` 也加入回歸測試，釘住已安裝 matcher 與 tracker allowlist 必須
  同時涵蓋它們。

- **`review-loop` 的觸發說明把單次 final publication 也納入（`fork`）。** Frontmatter
  現在只在已有或明確規劃第二輪回饋時觸發；多輪流程的最後發布仍會檢查，單次回覆與
  single-pass final draft 則明確跳過。Script 路徑也改為相對目前 skill directory 解析，
  不再 hard-code 另一個 agent 的安裝根目錄。

## 2026-08-23

### 修正

- **CI 在 Python 3.11 編不過：f-string 運算式裡不能有反斜線（`fork`）。**
  `scripts/check_upstream_updates.py` 的 `render_ticket_section()` 把跳脫寫在 f-string 裡
  （`{ticket['title'].replace('|', '\\|')}`）。這在 3.12 以後合法，在 3.11 是 `SyntaxError`，
  而 CI 的 `compileall` 矩陣同時跑 3.11 與 3.14——本機只有 3.14，所以寫的當下一切正常，紅燈只
  出現在 CI。跳脫移到 f-string 外面先算成 `title`。本機用 uv 的 3.11.15 實跑
  `python -m compileall scripts hooks skills/info-diet/scripts skills/review-loop/scripts`
  確認 exit 0。

- **Upstream check 工作流程沒有給 `gh` 任何憑證，於是每次都 fail closed（`fork`）。**
  檢查器用 `gh pr list` / `gh issue list` 查上游，但 Actions 裡的 `gh` 沒有 `GH_TOKEN` 就不能
  認證，兩個面向都回 `None`，檢查器照設計 fail closed（exit 2）。結果是紅燈寫著「無法列舉上游
  PR 與 issue」——看起來像上游查不到，其實是 token 沒給。工作流程的 `env` 補上
  `GH_TOKEN: ${{ github.token }}`。本機帶 token 實跑 `--strict` 確認 exit 0。

### 新增

- **強推規則的放行標記 `# force-push-ok: <理由>`（`fork`）。** `danger-zone-guard` 對 main／master
  的強推一律擋，沒有出口。但「壓縮這個 repo 的歷史」這類要求，強推本身就是被交代的事——一道沒有
  出口的閘門不會讓人放棄，只會讓人改用 `git push origin +main` 或 REST refs API，而那兩種寫法這條
  正則都看不見。比照 `fork_pr_guard` 的 `# upstream-ok:` 加上標記：**必須寫理由**（只寫
  `# force-push-ok:` 照擋），且**只對強推那條生效**——`rm -rf /` 與憑證外洩加了標記一樣擋。
  claude-code 與 codex 兩個版本同步修改，`hooks/danger-zone-guard/tests/run-tests.py` 補四條把
  這四個性質釘住。

## 2026-08-23

### 修正

- **上游檢查器只看 commit，PR 與 issue 兩個面向從來沒被查過（`fork`）。** `scripts/upstream_baseline.json`
  裡的 `reviewed_pr_through` 與 `reviewed_issue_through` 沒有任何程式讀它們，而報告照樣印成綠的——
  「查過沒發現」與「根本沒查」在一份綠報告裡長得一模一樣，而只有一個是真的。現在三個面向各一段，
  用 `--state all` 查（項目在兩次排程之間被開了又關，對本 fork 仍是從沒審過），`gh` 不可用時回報
  **Not checked** 並 fail closed（exit 2）。`tests/test_upstream_check.py` 12 條把 `None`（沒查成）
  與 `[]`（查過、沒有）必須產生不同報告文字與不同 exit code 這條分界釘住。
- **首次實查的結果**：PR #2（非 UTF-8 locale 下改讀 bytes）已合併且其 merge commit 是水位的祖先，
  本 fork 的 `no-emoji-guard.py:129` 確認已有該修正；issue #1 是使用問題。水位推進到 PR #2、issue #1。
  逐項判斷寫在 `FORK.md`。

## 2026-08-22

### 修正

- **安裝器不再放寬檔案權限。** 新加的 CodeQL 掃描第一次跑就指出四處：hook 檔以 `0o755` 寫入（world-readable、world-executable），而 skill 目錄刪不掉時的重試處理會先 `chmod 0o777`（world-writable）。這些 hook 只由安裝它們的使用者執行，其他本機帳號沒有理由讀得到或跑得動；刪除只需要 owner 的 rwx。四處都改成 `stat.S_IRWXU`（0o700）。一套 guardrail kit 不該是那個把權限放寬的東西。

### 新增

- **`phantom-pushback` skill（採自上游 `3baf40e`）。** 處理「AI 在結尾虛構一個你沒說過的立場，再來反駁你」這種失敗模式——它不是話多，叫它精簡沒有用，因為那段話看起來像有內容。判準只有一句：能不能指出你真的說過或寫過的東西支持那個立場？不能就刪。真正的批評（對程式碼、數字、計畫）不動；被埋在結尾的真實警告要移到最前面而不是刪掉。技能總數 11 → 12。
- **上游審視紀錄進 `FORK.md`。** 每個上游 commit 的採用／不採用與理由留在同一張表，`scripts/upstream_baseline.json` 推進到 `3baf40e`。

## 2026-08-21

### 新增

- **`fork` 上游更新排程檢查。** `.github/workflows/upstream-check.yml` 每週一 11:00（Asia/Taipei）比對 `agentcrew-academy/harness-starter-kit` 的 `main` 與 `scripts/upstream_baseline.json` 的 `reviewed_through`，有未審 commit 就讓 workflow 失敗並在 summary 列出 commit 與檔案清單。之前「有沒有新上游」全靠人記得去 fetch。
- **`fork` `.github/dependabot.yml`。** 本 kit 沒有套件 manifest，唯一可自動更新的依賴面是 workflow 裡釘住的 actions；每週一檢查一次。

## 2026-08-18

### 新增

- **`fork` `install.py --agent cursor` 與 `--agent codex`。** Cursor 寫入扁平的 `~/.cursor/hooks.json`（`version: 1` + event → `[{command}]`），shell 守衛掛在 `beforeShellExecution`，emoji 掛在 `preToolUse`。Codex 合併進既有 `~/.codex/hooks.json`，Windows 使用 Python 版與絕對路徑，避免 `python3 ~/.codex/hooks/...` 無聲失敗。`--agent all` 現在包含這兩個 target。
- **`fork` docs/cursor-install.md**（+ `.en.md`）：事件對照，以及 Cursor `stop` 不能否決、只能 follow-up 的限制。

### 變更

- **`fork` `verification-protocol` 新增有界 live validation。** UI、Production、OAuth、部署與外部服務驗證現在會先定義最小證據清冊與停止條件，限制為一筆唯一 smoke data、精準查詢、一次控制恢復與登入後原地續做，達標即停，避免重複驗證耗用真實資料與 quota。
- **`fork` Codex skill 安裝位置對齊現行契約。** `install.py --agent codex` 現在寫入 `~/.agents/skills/`，不再建立新的 legacy `~/.codex/skills/`；既有 legacy 內容保留。Codex 文件與 verifier 也明確區分腳本 live-fire 與 `/hooks` trust 檢查。
- **`fork` Codex 安裝驗證改為真實 payload live-fire。** verifier 現在會執行 5 種已註冊的 Codex hooks，缺少腳本會失敗，不再只驗 `hooks.json`。no-emoji-guard 也補讀真實 `apply_patch` payload 的 `tool_input.command`，只掃新增行並保留 transcript / `.srt` 路徑豁免，避免註冊正常卻 fail-open，或反過來攔住 emoji 移除。
- **`fork` POSIX hook 安裝會正規化為 LF。** 即使從 Windows CRLF checkout 在 WSL 執行安裝器，複製到 agent 目錄的 `.sh` 也不會因 `set: invalid option` 而失效；`.gitattributes` 同步固定 shell scripts 使用 LF。
- **`fork` Python hook 讀 Cursor payload。** `beforeShellExecution` 的指令在頂層 `command`，工具名是 `Shell`。擋下時回 `{"permission":"deny"}`；Claude Code 的 `exit 2` + stderr 與 Codex 的 `decision` JSON 維持不變。
- **`fork` Cursor `stop` 上的 claim-guard / lint-gate 改 follow-up。** Cursor 不能在回合結束後 veto，硬擋會假裝有保護。沒有 `last_assistant_message` 時 claim-evidence 仍 fail-open（與既有契約相同）。
- **`fork` lint-gate 的專案目錄也可來自 payload `cwd` / `workspace_roots`。** Cursor 使用者層 hook 的行程 cwd 是 `~/.cursor`，不能只用 `os.getcwd()`。

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

### 變更（上游）

- **編碼修正已送回上游並被接受**（[upstream#2](https://github.com/agentcrew-academy/harness-starter-kit/pull/2)）。
  上游接著補上 stdout／stderr 也要設成 UTF-8——hook 可能正確擋下、卻在印自己的訊息時
  因為 locale 編碼炸掉，使用者看到 traceback 而不是原因。該改法已拉回本 fork 的全部九支 hook。

### 新增（設定持久化）

- **`fork` no-emoji-guard 的設定改放腳本旁的 `no-emoji-guard.json`，重裝洗不掉。**
  起因是實際事故：安裝程式整支覆蓋 hook 腳本，把使用者刻意關掉的設定洗回「開啟」，而且無聲。
  現在支援 `{"enabled": false}`（保持安裝但關閉，開回去只要改一個字、即時生效不用重啟）與
  `{"exempt_path_substrings": [...]}`，優先於腳本內的常數；設定檔壞掉時回到內建預設（繼續擋），
  打錯字不該變成關掉護欄的方式。兩個平台版本各 5 案回歸測試，並納入 CI。

### 修正（安裝器：重複註冊）

- **同一支腳本改了參數後會被重複註冊。** 加上 `--codex` 讓指令字串變了，安裝器的比對是整串
  比對，於是把新的加在舊的旁邊——lint-gate 與 claim-ledger-tracker 在 Codex 上每次事件跑兩次，
  其中一次還是用舊行為。在真實機器上發生過（2026-08-20）。
  改為以**腳本路徑**比對：同一支腳本的舊註冊會被移除再寫入新的；清理無條件執行
  （不是只在「有新增」時），而且有清理就會寫回檔案，否則清掉的東西根本沒落地。
  使用者自己的其他 hook 不受影響。附回歸測試（連跑兩次驗證冪等）。

### 修正（跨 agent 協定）

- **Cursor 支援誤把 Claude Code 認成 Cursor，兩支 Stop 守衛因此不再攔截。**
  判斷式是 `payload.get("hook_event_name")`，但那個欄位 Claude Code 也會送（大寫的 `Stop`、
  `PreToolUse`）。於是 claim-evidence-guard 與 lint-gate——正好是「不准結束回合」那兩支——
  改印 Cursor 的 follow-up JSON 並回傳 0，在它們主要保護的平台上等於不再擋。
  既有測試抓不到，因為合成 payload 沒有 `hook_event_name`。
  改為只認 `cursor_version` 或 Cursor 自己的事件名（小寫 `stop`、`beforeShellExecution` 等）。
- **Codex 在 Windows 上裝到的是 claude-code 版 hook，協定不對。** test-gate、danger-zone、
  no-emoji 三支本來就有純 Python 的 codex 版，Windows 完全能跑，只是沒被選用；結果攔截時
  exit 2 且不印 JSON，Codex 讀不到。已改指向 codex 版。
- **lint-gate 與 claim-ledger-tracker 沒有免 jq 的 codex 版**，改由安裝器加 `--codex` 參數，
  讓 Windows 版用 Codex 的 JSON 協定回應（放行印 `{}`、攔截印 `decision: block`）；
  不加參數時 Claude Code 行為完全不變。
- 新增 `hooks/tests/run-agent-protocol-tests.py`（12 案，已進 CI）：用**貼近真實**的 payload
  驗證每支 hook 對三種 agent 各自回應正確的協定。已確認對修正前的版本會紅燈（2 案）。

### 修正（安裝器）

- **Windows 唯讀檔導致的 `PermissionError` 已處理**：`robust_rmtree` 會清掉唯讀位元再刪。
  git checkout 或編輯器留下的唯讀檔會讓 `shutil.rmtree` 直接噴錯。
- **但刪不掉時不再假裝成功。** 原本的寫法把錯誤 `except Exception: pass` 吃掉，接著用
  `dirs_exist_ok=True` 蓋上去：結果是舊版殘留檔留著、卻印出「copied」、exit 0。實測（檔案被
  另一個行程開啟時）確認會發生。現在改成明確報 `FAILED to replace`、整個資料夾原封不動、
  不印「Installation finished」、exit 1——exit code 也必須反映事實，否則 `&&` 串接會照樣往下走。
  兩案回歸測試進 CI（唯讀→修好並替換；鎖住→報失敗不宣稱），並確認對修正前的版本會紅燈。

### 修正（回歸）

- **`fork` 兩支 hook 被改回文字模式讀 stdin，已修回並加靜態檢查。** 新增 Antigravity 生命週期
  支援的那次改動，把 `read_payload()` 留在檔案裡但不再從 `main()` 呼叫——helper 成了孤兒，
  hook 悄悄退回依 locale 解碼。編碼測試當場抓到（2 案紅燈）。
  同時發現：用 grep 找 `stdin.buffer` **證明不了任何事**，那只證明字串存在。
  `hooks/tests/run-encoding-tests.py` 因此加了一道 AST 靜態檢查：任何 hook 只要真的呼叫
  `sys.stdin.read()`／`json.load(sys.stdin)`，或定義了 `read_payload()` 卻沒用，就紅燈。
  （用 AST 不用 grep，因為這些檔案的 docstring 本來就會提到那兩個呼叫，正是為了說明不要用。）

### 變更（文件）

- **`fork` 兩套新技能與 `gemini-md-template/` 改寫成英文**，與既有九套技能、`claude-md-template/`
  一致（那些檔案是給 agent 讀的，repo 內統一英文；`README`、`docs/` 仍以中文為主、英文放 `.en.md`）。
- **`fork` `gemini-md-template/GEMINI.md` 依它自己宣稱的減法原則重寫。** 原版寫了五段，其中包含
  深色模式、玻璃擬態、指定字型這類**個人審美**，以及會過期的語言版本號。拿掉這一行 AI 會不會犯錯？
  不會——那就不該出現在一份「每個專案都會載入」的全域規則檔裡。現在是它 README 本來就宣稱的
  三段結構（背景／硬閘門／判斷脈絡），偏好改成待填空格。
- **`fork` Antigravity 安裝指南的自動化建議改掉。** 原本建議把整個家目錄設為信任工作區並一次
  打開全部自動核准。信任範圍縮到專案資料夾，並把「關掉彈窗＝這包 hook 成為唯一防線，而它是
  攔截器不是沙箱」講明，自動化拆成兩階段。

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
