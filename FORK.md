# 關於這份 fork

本 repo：[SanHsien/harness-guard](https://github.com/SanHsien/harness-guard)
（原名 `harness-starter-kit`，2026-08-15 更名；GitHub 會自動轉址舊網址。
本機工作目錄仍叫 `harness-starter-kit`，同 voxprose 的做法。）

上游：[agentcrew-academy/harness-starter-kit](https://github.com/agentcrew-academy/harness-starter-kit)

這份 fork 加上 Windows 支援、第四個攔截工具，以及**可再現性**：換一台電腦，
一行指令就能裝出同一套環境。上游那套是寫給 macOS 與 Linux 的，在 Windows 上有三個
安裝步驟會失敗，而且三個都不會說。

**這份 fork 不打算回貢上游**，所以改動不受「上游會不會收」限制；但仍保留單向同步的能力，
上游有好東西可以拉進來。

---

## 加了什麼

| 新增 | 為什麼 |
|---|---|
| `scripts/install.py` | 一行指令重現整套設定：自動判平台、複製對應版本、**合併**（不是覆蓋）進 `settings.json`、先備份、原子寫入、寫完讀回驗證 JSON 仍合法。重跑不會重複註冊。 |
| `scripts/verify-install.py` | 餵合成 payload 給每個已安裝的 hook、實際執行、檢查回應。「讀設定檔然後宣布沒問題」正是這個 kit 存在要擋的那種無證據宣稱。 |
| lint-gate 專案級設定 `.lint-gate.json` | 全域註冊一次即可，沒有這個檔案的專案完全不受影響；哪個專案要開就在該專案根目錄丟一個檔案，立即生效、不用重啟。讓各專案的 agent 自己決定要跑什麼檢查。（Windows 版限定） |
| `hooks/*/windows/*.py` | claim-guard 與 lint-gate 的 Python 版。shell 版靠 `jq`，Windows 原生沒有 `jq`，而它們沒有 `jq` 時 exit 0——那代表「放行」。一個什麼都不擋的已註冊 hook，比沒裝更糟。 |
| `hooks/test-gate-guard/` | 第四個攔截工具。擋掉「測試指令與 `git commit`／`git push` 之間用 `;` 而非 `&&` 串接」的單條指令——那正是紅燈測試照樣出貨的形狀。來自一次真實事故，並附上它自己上線第一天誤報所產生的回歸測試。 |
| `settings-example.windows.json` | 絕對路徑、用 `python` 不用 `bash`、設定用參數不用 `VAR=value` 前綴。 |
| `docs/windows-install.md`（+ `.en.md`） | Windows 三個失敗模式，每個都在真實機器上實測過，各自附解法。 |
| `AGENTS.md` 改寫為單一真相源 | 安裝指引不再綁定單一 agent，任何 AI agent 讀這一份就夠。`CLAUDE.md` 縮成 Claude Code 專屬薄補丁。 |
| `.gitignore` 補 `__pycache__` | 上游誤追蹤了 6 個 `.pyc`。 |

---

## 可再現性：換一台電腦怎麼裝

```bash
git clone https://github.com/SanHsien/harness-guard.git
cd harness-guard
python scripts/install.py --dry-run --hooks all --skills all   # 先看會動到什麼
python scripts/install.py --hooks all --skills all             # 真的裝
# 完全關掉 Claude Code 再開
python scripts/verify-install.py                               # exit 0 才算裝好
```

三個設計上的取捨，都是刻意的：

- **不匯出個人 `settings.json`。** 那份檔案裡有本機路徑、啟用的 plugin、個人偏好，
  推上公開 repo 是外洩。`install.py` 改成把需要的區塊合併進目標機器既有的設定檔。
- **既有的 skill 資料夾不覆蓋**（除非 `--force`）。checkpoint 與 neat-freak 本來就要照個人
  檔案擺法調過，你調過的版本比原版值錢。
- **規則檔範本不自動裝。** `claude-md-template/` 是一段一段問過、確認適用才合併進既有
  `CLAUDE.md` 的東西，自動化只會把兩份規則疊成互相稀釋的一團。

---

## 文件語言慣例

- `README.md`、`AGENTS.md`、`CLAUDE.md`、`docs/*.md` 以**繁體中文為主**。
- 英文鏡像用 `*.en.md`（`README.en.md`、`docs/windows-install.en.md`）。改中文版時同步英文版。
- GitHub 的 About 欄位雙語。

`AGENTS.md` 是安裝與工作規則的**單一真相源**；`CLAUDE.md` 只放 Claude Code 專屬的路徑與
介面細節，不重複規則。改規則改 `AGENTS.md`。

---

## 從上游同步

```bash
git fetch upstream
git log --oneline HEAD..upstream/main    # 對面有什麼新東西
git merge upstream/main
```

會衝突的是被改過的上游檔案：`README.md`（已換成中文，英文搬到 `README.en.md`）、
`AGENTS.md`、`CLAUDE.md`、`hooks/README.md`、`.gitignore`。README 的衝突會最大，
因為主檔語言換了——解法是把上游的新內容併進 `README.en.md`，再把對應段落翻進 `README.md`。

合併之後，這份 fork 負責的兩件事要重新證明一次：

```bash
python hooks/test-gate-guard/tests/run-tests.py    # 預期 0 failures
python scripts/verify-install.py                   # 預期 exit 0
```

上游若改了 shell 版 hook 的判斷邏輯，`hooks/*/windows/` 對應的 Python 版要**手動**跟上——
兩邊是各自獨立的檔案，不是自動生成的。必須保持一致的是觸發詞與 fail-open 規則。

---

## symlink 注意事項

`.agents/skills/*` 是 git symlink，指向 `skills/`。Windows 上若沒開 Developer Mode 或
`core.symlinks=true`，它們會被 checkout 成內容是一行路徑字串的普通檔案。這無害——真正的
skill 在 `skills/`——但不要提交「把它們改成複本」這種修正。
