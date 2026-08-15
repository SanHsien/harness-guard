---
name: task-orchestrator
description: "Decompose complex multi-file or large-scale tasks into clean lifecycle stages: Research, Plan, Build, and Verify. Use for large refactoring, new feature implementation, or subagent workflow orchestration."
allowed-tools: Agent Read
---

# Task Orchestrator — 複雜任務拆解與上下文管理

本技能定義了大型工程與多階段任務的標準拆解工作流，確保 Agent 在高複雜度環境下保持上下文清爽、決策可溯源且驗證完備。

---

## 四階段執行模型 (Four-Stage Model)

```
[1. Research (調研)]
  └── 唯讀探索、定位關鍵檔案、確認依賴與邊界條件。禁止直接改動代碼。

[2. Plan (計畫)]
  └── 制定結構化實作步驟、確認關鍵決策點、列出受影響模組。

[3. Build (實作)]
  └── 循序建立或修改程式碼，模組化推進，遵循 SOLID/DRY 與防禦性原則。

[4. Verify (驗證)]
  └── 執行自動化測試、型別檢查與回歸驗證。確認 exit code 0 且零偽修正。
```

---

## 上下文防護策略 (Context Protection)

1. **避免單一對話過載**：
   - 當調研過程產生龐大日誌或需要多步搜尋時，可善用子代理人 (Subagent) 在獨立上下文處理，只回傳提煉後的結論。
2. **減法思維**：
   - 記錄產出時使用標準化的摘要結構，避免在主要交談記錄中堆積大段無關輸出。

詳細拆解實務見 [`references/decomposition-playbook.md`](references/decomposition-playbook.md)。
