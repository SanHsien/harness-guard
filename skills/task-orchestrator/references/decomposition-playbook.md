# 任務拆解劇本 (Task Decomposition Playbook)

## 典型場景拆解步驟

### 場景 A：跨平台功能移植
1. **Research**：比對目標平台與現有平台之 API 差異（如 Shell vs Python, POSIX vs Windows 路徑）。
2. **Plan**：列出需移植之模組清單，定義共用介面與平台分支邏輯。
3. **Build**：以標準庫優先方式實作，確保各平台邏輯一致。
4. **Verify**：跨平台跑合成 payload 與真實環境測試。

### 場景 B：新增安全攔截器 (Guardrail Hook)
1. **Research**：分析歷史事故模式與常見繞過漏洞（如引號跳脫、多參數切換、換行串接）。
2. **Plan**：定義攔截規則（Regex/AST）、決定攔截時機（PreToolUse vs Stop）與 fail-open 邊界。
3. **Build**：編寫 hook 核心邏輯與合成測試案例（包含正向阻止與負向放行）。
4. **Verify**：執行回歸測試與 Live Fire 驗證。
