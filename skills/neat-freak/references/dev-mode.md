# 開發 repo 附加流程（條件載入）

**載入條件**：本次會話碰了有 API / 環境變數 / 資料庫 / 套件發佈的 repo（如 PDT-learning）。純文檔會話（多數情況）不載入本檔。

## 代碼層變更 → 文檔層變更

| 本次對話發生的事 | 要改的文件（按受眾） |
|---|---|
| 新增 API / 路由 | 專案根 markdown 路由清單 · `docs/integration-guide.md` API 速查表 · `docs/architecture.md` Routes 小節 |
| 新增 / 改名 環境變數 | 專案根 markdown 環境變數表 · `docs/operator-runbook.md` 環境變數章節 · `docs/integration-guide.md`（如果下游要配） |
| 新增資料庫表 / 欄位 | 專案根 markdown 資料庫表 · `docs/architecture.md` Data Model |
| 新增 / 改動 使用者流程 | 專案根 markdown 使用者流程 · README 相關命令列範例 · `docs/handoff.md` What Exists Today |
| 新增大特性（跨多文件） | 以上全部 + `docs/architecture.md` 新增章節 + `docs/handoff.md` 已完成清單 |
| 新增術語 / 改命名 | `docs/integration-guide.md` 術語表（如果有）+ 全域搜尋舊術語替換 |
| 部署參數 / 基礎設施變化 | `docs/operator-runbook.md` · 專案根 markdown 部署章節 |
| 下游專案接入方式變化 | 下游專案的 `docs/<integration>.md` · 上游專案的 `integration-guide.md` |

## 開發專案 GATE 附加清單

SKILL.md 第二步 GATE 的開發專案專屬條目：

- [ ] 新增 API 路由：**在 integration-guide 和 architecture 都出現了**
- [ ] 新增環境變數：**在 runbook 和專案根 markdown 都出現了**
- [ ] 新增資料庫表：**在 architecture 的 Data Model 和專案根 markdown 都出現了**
- [ ] README 的安裝 / 運行步驟跟代碼一致
- [ ] CLAUDE.md / AGENTS.md 提到的路徑 / 命令 / 工具 / 環境變數在代碼中真實存在

## 跨專案影響檢查（開發版）

最容易漏改的場景：

- **上游 API 變了 → 下游 SDK 文檔**：協議變化必須兩邊對齊
- **共享子域 / 路由 / 環境變數改了 → 所有 consumer 專案的 setup 文檔**
- **認證中台變更 → 所有接入應用的 integration guide**
- **公共元件 / 基礎設施升級 → 各專案 operator-runbook 提及版本號的地方**

判斷方法：這次改的東西有沒有 SDK、子域、共享配置、跨行程協議？有就要在所有依賴專案裡搜一遍提到這件事的文檔。

## 文檔結構通用約定

新增一個能力（API、flow、特性）的標準動作是**四處都補**：

1. **integration-guide / 外部視角文檔**：怎麼用（curl / SDK 範例 / 錯誤碼表）
2. **architecture**：怎麼運作（資料流、狀態機、設計取捨）
3. **runbook**：怎麼運維（冒煙命令、故障排查、環境變數）
4. **handoff / CHANGELOG**：已完成

API 速查表、環境變數表、術語表是高頻查詢的結構化資訊，**必須保持「所見即最新」**。

> 注意：許多 repo 已有自己的機械閘門（`validate_docs.py`、`spec_lint.py`、PostToolUse hooks）。有閘門的 repo 以閘門輸出為準，本表當補充 checklist 用。
