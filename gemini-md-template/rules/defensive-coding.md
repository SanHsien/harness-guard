# 防禦性程式設計與邊界安全規範 (Defensive Coding & Security Rule)

## 核心要求
1. **防禦性設計 (Defensive Design)**：
   - 針對外部輸入、檔案讀寫、網路傳輸與 API 回傳值進行嚴格的空值 (`null` / `undefined` / `None`) 與邊界檢查。
   - 讀寫檔案前確認目錄是否存在；解析 JSON 或結構化資料時加上異常捕捉與合理的失敗處理。

2. **安全邊界 (Boundary Protection)**：
   - 嚴格限制操作範圍於當前工作專案內，未經授權禁止讀寫或變更專案外的系統敏感路徑與設定檔。
   - 絕對禁止在指令或代碼中明文硬編碼或外傳 API Key、Token、私鑰或敏感憑證。
