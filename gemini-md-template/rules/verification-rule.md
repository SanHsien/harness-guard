# 修改即驗證與零偽修正規範 (Modify-Then-Verify & Zero-Dummy Rule)

## 核心要求
1. **修改後立即驗證**：
   - 每次新增或修改程式碼後，必須主動執行語法檢查 (Linting)、編譯測試 (Build) 或單元測試 (Unit Test)。
   - 不准在未親自執行測試的情況下宣稱「已修復」、「已完成」。

2. **零偽修正 (Zero Dummy Fix)**：
   - 嚴禁以註解掉測試案例、註解掉斷言、吞掉例外 (Empty Exception Handler / catch-all pass) 或回傳假資料 (Dummy Fallback) 的方式製造通過的假象。
   - 遇到測試失敗時，先查看完整錯誤日誌與 Stack Trace，針對根因進行實質修復。

3. **邊界與回歸防護**：
   - 修復 Bug 時，必須確保未破壞既有功能，並在可能的情況下補上回歸測試。
