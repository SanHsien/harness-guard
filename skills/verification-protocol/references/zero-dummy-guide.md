# 零偽修正指引 (Zero-Dummy Guide)

偽修正（Dummy / Fake Fix）是指「在表面上讓測試或程式碼不報錯，但實際上破壞了業務邏輯或掩蓋了真實問題」的行為。

---

## 常見偽修正型態與正確做法

### 1. 吞掉異常 (Swallowing Exceptions)
- **錯誤做法**：
  ```python
  try:
      fetch_data()
  except Exception:
      pass  # 假裝沒事
  ```
- **正確做法**：
  - 診斷 `fetch_data()` 為什麼拋出異常（是網路問題、認證失敗還是資料格式不符）。
  - 精確捕捉特定例外並進行合適的重試或錯誤提示處理。

### 2. 弱化或註解測試斷言 (Weakening Assertions)
- **錯誤做法**：
  ```python
  # assert result == 42
  assert result is not None  # 測試太難過，把斷言放水
  ```
- **正確做法**：
  - 修正運算邏輯，直到 `result == 42` 真正成立。

### 3. 未完成 Placeholder (TODO / Mock Data in Production)
- **錯誤做法**：
  ```typescript
  function calculateTax(amount: number) {
      // TODO: implement later
      return 0;
  }
  ```
- **正確做法**：
  - 一次性完整實現正確的計算公式與邊界處理。
