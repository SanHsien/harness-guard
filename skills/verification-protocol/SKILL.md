---
name: verification-protocol
description: "Enforce modify-then-verify and zero-dummy standards. Use when modifying code, running tests, diagnosing test errors, validating builds, or ensuring genuine verification evidence before completion."
allowed-tools: Bash Agent Read
---

# Verification Protocol — 修改即驗證與零偽修正作業流程

本技能落實最高規格之軟體開發驗證協議：**「修改代碼即自動執行驗證、日誌診斷優先、嚴禁偽修正 (Zero-Dummy)」**。

---

## 核心原則 (Core Rules)

1. **修改即驗證 (Modify-Then-Verify)**：
   - 只要新增、修改或重構程式碼，在回報用戶前必須在終端實際執行對應的測試、建置或 Linting 指令。
   - 禁止僅憑代碼視覺檢查即宣稱「已修復」或「測試通過」。

2. **零偽修正 (Zero-Dummy)**：
   - 遇到測試失敗時，嚴禁：
     - 註解掉失敗的測試案例或斷言。
     - 吞掉例外錯誤（如 `except Exception: pass`）。
     - 回傳假資料或 Hardcoded Dummy Fallback 掩蓋問題。
   - 詳見 [`references/zero-dummy-guide.md`](references/zero-dummy-guide.md)。

3. **日誌診斷優先 (Log-First Diagnosis)**：
   - 先完整讀取 Stack Trace 與失敗行號。
   - 查明根因（Root Cause）後才進行精準修改，嚴禁盲改。

---

## 驗證流程 (Verification Flow)

```mermaid
graph TD
    A[代碼變更完成] --> B[識別專案技術棧與測試指令]
    B --> C[實際執行測試 / 建置指令]
    C --> D{指令 Exit Code == 0 ?}
    D -- 是 --> E[記錄驗證證據與日誌摘要]
    D -- 否 --> F[讀取完整 Stack Trace 分析根因]
    F --> G[修復根因（非偽修正）]
    G --> C
    E --> H[回報完成並附上真實測試數據]
```

---

## 技術棧測試矩陣 (Test Matrix)

常用指令請查閱 [`references/test-matrix.md`](references/test-matrix.md)。
例如：
- Python: `pytest -v`, `python -m unittest`
- Node/TS: `npm test`, `bun test`, `pnpm test`, `npx vitest run`
- Go: `go test ./...`
- Rust: `cargo test`
- .NET: `dotnet test`
