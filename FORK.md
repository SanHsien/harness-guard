# 關於這份 fork

上游：[agentcrew-academy/harness-starter-kit](https://github.com/agentcrew-academy/harness-starter-kit)

上游那套寫給 macOS 與 Linux，在 Windows 上有三個安裝步驟會失敗，而且三個都不會說。
這份 fork 補上 Windows 支援、兩個攔截工具、跨 agent 安裝，以及可再現性：換一台電腦，
一行指令裝出同一套環境。

**回貢的判準：修的是上游的 bug 就送回去，這裡獨創的東西就留在這裡。**
上游的 hook 在非 UTF-8 locale 下會靜靜失效，那是他們的 bug，已送
[upstream#2](https://github.com/agentcrew-academy/harness-starter-kit/pull/2) 並被接受；
他們後續還補上 stdout 的部分，也拉回本 fork 了。反過來說，Windows 版建置、第四與第五個攔截工具、
安裝器與驗證器都是本 fork 的產物，不是在修上游的東西，就不必送去佔他們的審查時間。

逐版改了什麼看 [`CHANGELOG.md`](CHANGELOG.md)。本檔只講與上游的差異、怎麼同步。

---

## 與上游的差異

| | |
|---|---|
| `scripts/install.py` | 一行裝完：判平台與目標 agent、**合併**而非覆蓋設定檔、先備份、原子寫入、寫完讀回驗證、可重跑；支援 Claude Code、Antigravity skills、Cursor、Codex |
| `scripts/verify-install.py` | 實際執行每支已安裝的 hook 並檢查回應，不是讀設定檔宣布沒問題 |
| `hooks/test-gate-guard/` | 擋掉單條指令用 `;`（而非 `&&`）串接測試與 `git commit`／`git push` |
| `hooks/danger-zone-guard/` | 擋掉根目錄／家目錄遞迴刪除、刪 `.git`、保護分支強推、憑證外洩 |
| `hooks/*/windows/*.py` | claim-guard 與 lint-gate 的 Python 版（另兩支本來就是純 Python 單檔，三平台共用） |
| `hooks/tests/run-encoding-tests.py` | 非 UTF-8 locale 下的回歸測試——中文 payload 曾讓每支 hook 靜靜失效 |
| `.lint-gate.json` | lint-gate 專案級開關：全域註冊一次，各專案自己決定要不要跑、跑什麼 |
| Antigravity／Gemini 支援 | `docs/antigravity-install.md`、`gemini-md-template/`、`install.py` 多 agent 目標 |
| Cursor／Codex 安裝器 | `install.py --agent cursor|codex`；Cursor 寫扁平 `hooks.json`，Codex 合併進既有 `hooks.json` 並用絕對路徑 |
| 兩套新技能 | `verification-protocol`、`task-orchestrator` |
| `AGENTS.md` | 改寫為單一真相源，任何 agent 讀這份就夠；`CLAUDE.md` 縮成 Claude Code 薄補丁 |
| 文件語言 | 繁體中文為主，英文放 `*.en.md` 鏡像 |

---

## 換一台電腦怎麼裝

```bash
git clone https://github.com/SanHsien/harness-guard.git
cd harness-guard
python scripts/install.py --dry-run --hooks all --skills all   # 先看會動到什麼
python scripts/install.py --hooks all --skills all
# 完全關掉 agent 再開
python scripts/verify-install.py                               # exit 0 才算裝好
```

三個刻意的取捨：

- **不匯出個人設定檔。** 那裡面有本機路徑與個人偏好，推上公開 repo 就是外洩。
  `install.py` 改成把需要的區塊合併進目標機器既有的設定。
- **既有 skill 資料夾不覆蓋**（除非 `--force`）。checkpoint 與 neat-freak 本來就要照個人
  檔案擺法調過，調過的版本比原版值錢。
- **規則檔範本不自動裝。** 那是要一段一段確認才併進既有規則檔的東西，自動化只會疊出
  兩份互相稀釋的規則。

---

## 從上游同步

```bash
git fetch upstream
git log --oneline HEAD..upstream/main
git merge upstream/main
```

衝突會出現在被改過的上游檔案：`README.md`（主檔已換中文，英文在 `README.en.md`）、
`AGENTS.md`、`CLAUDE.md`、`hooks/README.md`、`.gitignore`。README 衝突最大，解法是把上游
新內容併進 `README.en.md`，再把對應段落翻進 `README.md`。

合併後必須重新證明一次：

```bash
python hooks/test-gate-guard/tests/run-tests.py
python hooks/danger-zone-guard/tests/run-tests.py
python hooks/tests/run-encoding-tests.py
python scripts/verify-install.py
```

上游若改了 shell 版 hook 的判斷邏輯，`hooks/*/windows/` 要**手動**跟上——兩邊是各自獨立的
檔案，不是生成的。必須保持一致的是觸發詞與 fail-open 規則。

---

## symlink

`.agents/skills/*` 是指向 `skills/` 的 git symlink。Windows 上沒開 Developer Mode 或
`core.symlinks=true` 時會被 checkout 成內容是路徑字串的普通檔案。無害，但不要提交
「把它們改成複本」這種修正。
