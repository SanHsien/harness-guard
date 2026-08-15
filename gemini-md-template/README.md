# gemini-md-template

給 Google Antigravity (AGY) 與 Gemini CLI 的起手規則範本，照 Antigravity Customization System 官方規範設計。

---

## 為什麼需要這份範本

Antigravity 具備強大的階層式規則載入機制（`~/.gemini/GEMINI.md` -> 專案根目錄 `GEMINI.md` -> `.agents/rules/*.md`）與技能漸進式載入（Progressive Disclosure）。

這份範本遵循**減法原則**：
- 只有三個核心區塊：**身分背景、硬閘門、判斷脈絡**。
- 不放無效的客套話，每一行都確保「拿掉這一行，AI 是否可能犯錯？不會就刪掉」。

---

## 目錄結構

```
gemini-md-template/
├── GEMINI.md                    # 主起手範本（可放置於 ~/.gemini/GEMINI.md 或專案根目錄）
├── README.md                    # 本說明檔
└── rules/                       # 可選子規則檔（可放置於 ~/.gemini/config/rules/ 或 .agents/rules/）
    ├── verification-rule.md     # 修改即驗證與零偽修正規範
    ├── subagent-workflow.md     # 子任務分派與 Context 隔離規範
    └── defensive-coding.md      # 防禦性程式設計與邊界安全規範
```

---

## 安裝方式

### 方式一：一行指令安裝（推薦）

```bash
python scripts/install.py --agent antigravity --skills all
```

此指令會將本 repo 的所有 skills 同步至 Antigravity 的全域技能目錄（`~/.gemini/config/skills/`）。

### 方式二：手動合併起手範本

1. 打開你的全域規則檔（Windows 為 `C:\Users\<使用者名稱>\.gemini\GEMINI.md`，Linux/macOS 為 `~/.gemini/GEMINI.md`）。
2. 若已有檔案，**請使用合併，不要直接覆蓋**。一段一段檢視並確認適合你的條目。
3. 若為新建立，複製 `GEMINI.md` 並填寫當中的專屬資訊（語言、偏好技術棧、時區）。
