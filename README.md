> [English](README.en.md) | 中文版

# 五個讓 AI 守規矩的小工具、十一套現成的工作流程，加上起手規則檔

> **這是一份 fork。** 多了五個攔截工具的 Windows 版、跨 Agent 支援（Claude Code、OpenAI Codex、Google Antigravity、Cursor），以及一支「用實際執行證明裝好了」而不是假設裝好了的驗證腳本。用 Windows 的話從 [`docs/windows-install.md`](docs/windows-install.md) 開始，用 Antigravity 從 [`docs/antigravity-install.md`](docs/antigravity-install.md) 開始。
>
> 每一版改了什麼看 [`CHANGELOG.md`](CHANGELOG.md)；跟上游的差異與同步方式看 [`FORK.md`](FORK.md)。

你有沒有遇過這種事：你明明告訴 AI「每次改完程式碼都要先跑測試」，它前三次乖乖照做，第四次就忘了，而且忘記的時候完全不會講；或者它執行了危險的指令、刪掉未追蹤的檔案。

這就是我做這些東西的原因。

問題出在「規則只是一段文字」。你把規則寫下來，AI 讀了、也懂了，但它沒有義務照做。聊天內容一長，那段文字就被沖淡了。它不是故意騙你，是真的沒放在心上。

這裡的做法是：**不要拜託它，直接擋住它。** 把「希望它做到的事」變成電腦會自動執行的檢查，它沒做到就過不去。

---

## 不會寫程式也能裝

不用自己動手。把這個網頁的網址複製起來，貼給 Claude Code、Codex 或 Google Antigravity，跟它說：

> 幫我把這個裝起來，我不會寫程式，你一步一步來，每步告訴我在做什麼。

這個資料夾裡有一份寫給 AI 看的說明書（就是那個叫 `AGENTS.md` 的檔案），它會照著上面的步驟問你需求、幫你裝、幫你改設定，並且用你聽得懂的話講。你只要回答它的問題就好。

---

## 會開終端機的話：一行裝完（本 fork 新增）

換一台電腦要裝出同一套環境，不用照著文件一步步做：

```bash
# Claude Code 環境安裝
python scripts/install.py --dry-run --hooks all --skills all

# Google Antigravity (AGY) 環境安裝
python scripts/install.py --agent antigravity --skills all

# 全生態一次安裝
python scripts/install.py --agent all --hooks all --skills all
```

先看它打算動哪些檔案、往設定檔加哪幾行。確認沒問題再拿掉 `--dry-run` 跑一次。

它會自動判斷你的作業系統挑對應版本（Windows 挑 Python 版），**合併**進你既有的設定檔而不是覆蓋，動手前先備份，寫完再讀回來確認 JSON 還是合法的。重跑不會重複註冊，已經存在的 skill 資料夾也不會被蓋掉——你調整過的版本比原版值錢。

然後重啟你的 Agent，再跑：

```bash
python scripts/verify-install.py
```

exit code 0 才算裝好。這支腳本不看設定檔臉色，它直接把每個 hook 叫起來執行一次，看它是不是真的會擋。

---

## 名詞先解釋幾個

**AI Agent**：可以直接在電腦上幫你寫程式、改檔案的 AI 助手（如 Claude Code, Codex, Antigravity, Cursor）。

**hook（掛鉤）**：可以想成門口的警衛。你可以規定「AI 每次要動手寫檔案或執行指令之前，先讓警衛檢查一下」，警衛說不行就真的不行。這不是提醒，是攔截。

**skill（技能）**：一份寫好的做事步驟。你叫它的名字，AI 就照那套步驟做，不用你每次重講一遍。

**lint**：自動幫你挑出小毛病的檢查工具。名字來自洗衣機的濾網，專門把衣服上的棉絮挑出來。

---

## 五個攔截工具

每一支底下提供跨平台與各 Agent 的適配版本，判斷邏輯一模一樣。

### 1. claim-guard：抓它嘴上說有、實際沒做
AI 跟你說「我測試過了，沒問題」，但它根本沒跑過測試。這個工具一支腳本在旁邊默默記帳，另一支在它想結束對話的時候跳出來對帳。說測試通過？帳本裡要有跑測試紀錄。說找不到檔案？帳本裡要有搜尋紀錄。對不上就攔下。

### 2. no-emoji-guard：把表情符號擋在門外
照 Unicode 官方定義嚴格判斷，自動過濾正式文件、程式碼註釋與 Commit 訊息中的 Emoji 笑臉與裝飾符號。刻意保留排版用的箭頭與標記符號。

### 3. lint-gate：檢查沒過就不准收工
在 AI 想結束 turn 的時候自動跑一次檢查指令。Windows 版支援專案根目錄 `.lint-gate.json` 動態啟用，全域註冊一次，有配置的專案立即生效。

### 4. test-gate-guard：測試紅燈不准出貨
擋掉單條指令中「測試指令與 `git commit`/`git push` 之間用 `;` 或換行而非 `&&` 串接」的高危行為，避免測試失敗卻依然提交代碼。支援 pytest, npm, bun, deno, playwright, jest, vitest, cargo 等。

### 5. danger-zone-guard：高危指令與越界防護（本 fork 新增）
在指令執行前攔截毀滅性操作：
- 根目錄/家目錄遞迴刪除（如 `rm -rf /`, `rm -rf ~`, `rd /s /q C:\`）。
- 誤刪 `.git` 版本庫目錄。
- 強制推送保護分支（如 `git push --force origin main/master`）。
- 未加密洩漏或傳輸 `.env`、私鑰金鑰檔案。

---

## 十一套工作流程 (Skills)

1. **explain**：高中生聽得懂的白話重述，不准中英夾雜與堆砌術語。
2. **polite**：專業修辭與溫暖商務語氣轉換，不為對方憑空編造處境。
3. **first-principles**：第一性原理思考與探索未知。
4. **checkpoint**：收工閉環（工作日誌、事實對帳、精確提交推送）。
5. **neat-freak**：事實對帳引擎，機械式盤點專案與檔案現況。
6. **review-loop**：防止長文件修訂時段落無聲消失，具備段落鎖定與 Web 審閱介面。
7. **info-diet**：盤點個人注意力與瀏覽資訊結構，純本地運算、隱私保護。
8. **asd-ste100**：Simplified Technical English 改寫，消除多義詞與多構句。
9. **iso-24495**：ISO 24495-1 淺白語言改寫，雙語技法。
10. **verification-protocol**（本 fork 新增）：修改即驗證與零偽修正作業流程，禁止註解測試或以假資料掩蓋問題。
11. **task-orchestrator**（本 fork 新增）：大型與多階段任務拆解（Research → Plan → Build → Verify）與 Context 管理。

---

## 起手規則檔範本

- **`claude-md-template/`**：依 Anthropic 官方指引精簡編寫的 `CLAUDE.md` 起手範本與可選規則檔。
- **`gemini-md-template/`**（本 fork 新增）：依 Google Antigravity / Gemini 規範編寫的 `GEMINI.md` 全局與專案規則範本。

---

## 裝之前，先讓 AI 把腳本讀給你聽

這些東西會攔截 AI 的動作，影響你之後所有的工作。裝之前讓它把每支腳本讀一遍、或至少解釋
每支在做什麼。這句話對這個資料夾成立，對你在網路上看到的任何一包腳本都成立——看起來方便
不是裝它的理由。

---

## 授權

MIT License，見 [`LICENSE`](LICENSE)。

這個 kit fork 自 [agentcrew-academy/harness-starter-kit](https://github.com/agentcrew-academy/harness-starter-kit)，
其中幾支 hook 又改寫自更早的作品，原作者與出處列在 [`NOTICE`](NOTICE)。你要轉發或再利用的話，
把那份檔案一起留著——那是 MIT 唯一真正要求你做的事。
