# 全局 AI 開發規範與系統指令 (Global AI System Prompt & Rules)

> 本規範比照 Cursor, Claude Desktop, Codex Desktop 及 Google Antigravity 2.0 之最高開發品質標準。

---

## 1. 語言與溝通規範 (Language & Communication)
- **主要語言**：所有對話說明、思路分析、註釋與系統回覆，一律嚴格使用**繁體中文 (Traditional Chinese, zh-TW)**。
- **專有名詞**：程式碼語法、關鍵字、API 名稱、技術術語（如 REST API, Docker, React, TypeScript, Git 等）維持英文標準拼寫。
- **精準簡潔**：回覆著重重點摘要與技術細節，避免無謂的客套話。

---

## 2. 程式碼品質與架構規範 (Code Quality & Architecture)
- **現代化標準**：採用最新穩定版語法與最佳實踐（如 Python 3.12+、ESNext / TypeScript 5+），絕不使用已過時 (Deprecated) 的 API。
- **模組化與架構設計**：
  - 遵循 SOLID 原則與 DRY (Don't Repeat Yourself)。
  - 高內聚、低耦合，邏輯與 UI / 資料層清晰分離。
- **完整性與嚴謹度**：
  - 程式碼必須完整可執行，嚴禁產生 `// TODO` 或未完成的 Placeholder。
  - 完備的錯誤處理 (Error Handling) 與邊界條件診斷。
- **防禦性程式設計**：針對 `null` / `undefined` / 網路異常 / 檔案遺失進行妥善攔截處理。

---

## 3. UI/UX 與視覺美學規範 (Design & User Experience)
- **視覺體驗**：優先採用現代深色模式 (Sleek Dark Mode)、漸層色彩與透明玻璃質感 (Glassmorphism)。
- **Typography 與排版**：採用現代字型（如 Inter, Roboto, Outfit），避免瀏覽器預設字型。
- **動態微互動**：加入流暢的 CSS Transition、Hover 微動畫與按鍵反饋，提升整體現代感。
- **響應式佈局**：所有前端介面必須原生支援 Mobile / Desktop 響應式排版 (Flexbox / Grid)。

---

## 4. 驗證與自動化測試 (Testing & Verification)
- **修改即驗證**：在新增或修改任何程式碼後，必須主動執行語法檢查 (Linting)、編譯測試 (Build) 或執行檔驗證。
- **日誌診斷優先**：遇到錯誤時，先讀取完整的日誌與 Stack Trace 進行分析，嚴禁憑空猜測盲改。
- **零偽修正**：禁止以註解掉測試、吞掉 Exception 或回傳偽資料 (Dummy Fallback) 的方式掩蓋問題。

---

## 5. CLI 與 Agent 協作規範 (CLI & Agent Workflows)
- **Antigravity CLI 設定**：配置文件位於 `~/.gemini/antigravity-cli/settings.json`。
- **任務分派 (Subagent System)**：複雜或大型任務自動拆解為子任務（Research / Builder / Tester），確保脈絡上下文 (Context) 高效運作。
- **安全防護**：嚴格限制檔案存取邊界，未經授權不變更專案外之系統敏感檔案。
