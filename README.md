# Harness Starter Kit

三支 Claude Code hook 與兩個 skill，處理同一個問題：**寫在 CLAUDE.md 裡的規則，模型會忘。**

規則是文字，文字沒有強制力。模型今天照做，明天 context 一長就漂掉，而且漂掉的時候不會告訴你。這裡的東西都是同一種解法——把「希望模型照做的事」改寫成系統會執行的閘門，模型不照做就過不去。

MIT 授權，拿去改。第三方來源見 [NOTICE](NOTICE)。

---

## hooks/

### claim-guard — 攔下沒有證據的完成宣稱

兩支腳本一組，缺一不可。

`claim-ledger-tracker.sh`（PostToolUse）默默記錄這個 session 跑過哪些驗證類指令、做過哪些搜尋。`claim-evidence-guard.sh`（Stop）在收工時比對：

- 回覆裡宣稱「驗證通過 / 測試通過 / 實測跑通」→ 帳本必須有對應的驗證指令紀錄
- 回覆裡做出「找不到 / 不存在 / 沒有這個」的負向斷言 → 帳本必須有搜尋動作紀錄

查無證據就擋下，不准結束這一輪。

會需要這個，是因為「我已經測過了」這句話的成本太低。模型可以在完全沒跑過測試的情況下說出它，而且語氣跟真的跑過一模一樣。純 bash + jq，不呼叫模型，不花 token。

安全失效模式：欄位缺失或 jq 失敗一律放行。它只在「有宣稱、且零證據」時才擋。

### no-emoji-guard — 擋下寫入內容裡的 emoji

判準依 Unicode UTS #51 官方資料（emoji-data.txt v17.0），不是憑感覺列黑名單：

1. `Emoji_Presentation=Yes` 的字元（預設就以彩色 emoji 呈現）
2. `Extended_Pictographic` 字元後接 VS16（U+FE0F，被明確要求以 emoji 呈現）

刻意不擋 `✓ ✕ → ← ↑ ↓` 與未接 VS16 的 `© ® ™`——這些是排版符號不是 emoji。

逐字稿與外部原檔歸檔自動放行。若你有整棵子樹要放行（例如 Obsidian vault 裡的到期日標記是 Tasks plugin 的功能語法，清掉會弄壞待辦追蹤），改檔頭的 `EXEMPT_PATH_SUBSTRINGS`。

已知限制：只掃當下要寫入的原始字元，掃不到 HTML numeric entity。

### lint-gate — 檢查沒過就不准收工

Stop hook。跑你指定的檢查指令，有錯就把錯誤丟回去要模型修完再結束。設定 `LINT_CMD` 與 `FAIL_PATTERN` 兩個變數即可套到任何專案。

裡面有一段 `stop_hook_active` 判斷務必留著：沒有它的話，修不好的錯誤會讓模型永遠結束不了這一輪。這是自己寫 Stop hook 最容易踩的坑。

---

## skills/

### checkpoint — 一次做完的收尾流程

寫日誌、選擇性 commit、push、驗證遠端狀態。重點在「一次」：主線只建立一份收尾計畫，避免同一件事被記錄兩遍或倒填。

### neat-freak — 事實對帳引擎

對帳的不是格式而是事實：狀態、版本、排期、金額、待辦。`scripts/enumerate.sh` 先做機械枚舉產出不可偽造的盤點證據，再據以修檔——不是讓模型憑印象說「我同步好了」。

兩個 skill 都需要按你自己的檔案結構調整。`references/sync-matrix.md` 是範本不是規格，左欄換成你的事實類型、右欄換成你的檔案佈局才有用。

---

## 安裝

hook 腳本放進 `~/.claude/hooks/`，skill 放進 `~/.claude/skills/`，然後在 `~/.claude/settings.json` 註冊。註冊範例見 [settings-example.json](settings-example.json)。

註冊後要**重開 session** 才會生效——hook 是在 session 啟動時載入的。

裝之前先自己讀過每一支腳本。這些東西會攔截你的工具呼叫，不該在沒讀過的情況下裝進去。

---

## 這些不是全部

這裡是三支獨立、可以單獨使用的工具。它們背後那套「什麼該做成 hook、什麼該留在 CLAUDE.md、什麼該做成 skill」的判斷方法，以及一整套踩坑紀錄，在另一份付費資產包裡：<https://agentcrew.cc>

免費的這三支不會過期也不會被拿掉。
