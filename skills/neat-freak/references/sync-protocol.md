# neat-freak Sync Protocol

你是知識庫編輯。輸入是一份 manifest：

- `mode: scoped | full`
- `memory_mode: read-only | update`
- `fact_list`（事實 → 波及檔案）
- active neat-freak skill dir、memory dir、vault、project roots

本協議只做事實對帳；不寫 session daily、不 commit、不 push。

## 1. 枚舉與載入路由

先執行 `<neat-freak-skill-dir>/scripts/enumerate.sh`：

```bash
<enumerate.sh> --memory <memory-dir> --vault <vault> [<project-root> ...]
```

保留輸出。若後續有修改，完成後重跑；最終摘要只貼最後一次原樣輸出。沒有最終 enumerate 證據即未完成。

只載入必要內容：

- 兩種模式都讀：fact list 波及主檔、今日 daily、對應 repo instruction。
- `scoped`：只加讀 enumerate 命中檔與 fact list 關鍵字在 memory index 命中的條目。
- `full`：再讀 memory index、今日相關的主檔／project docs、enumerate 命中檔；fact list 為空時以本 session 最近修改檔與今日 daily 為起點。
- 只有路徑無法解析才讀 `agent-paths.md`。
- 只有影響映射不確定才讀 `sync-matrix.md`。
- 只有 API、env、DB、部署或跨專案介面變更才讀 `dev-mode.md`。

禁止全量讀 rollout summaries、整個 memory topic tree、整個 vault 或所有 repo docs。先用 `rg` 定位，再讀命中段落。

產出內部文件清單，每檔標 `checked | edit | skip`。

## 2. GATE

編輯前逐項判定；用代碼回報，通過項可壓成範圍（例如 `G1-G10 pass; G11 skip`），失敗項必須展開證據：

- G1 文件清單每檔皆已判定。
- G2 daily 完成事項與主檔 `- [x] ... ✅ YYYY-MM-DD` 一致。
- G3 改期／取消已更新主檔日期或狀態。
- G4 新待辦只在單一來源檔（SSOT），且符合你自己的待辦格式規範。
- G5 同一開放待辦只有一個 SSOT。
- G6 對外承諾已反映「下一步、誰的球、追蹤日期」。
- G7 memory index links 存在。
- G8 已讀記憶 description 與內容一致、無可辨識矛盾。
- G9 待辦／狀態沒有相對時間。
- G10 stakeholder 身分已用主檔或分類規則核實。
- G11 開發 repo 的 API/env/DB/docs 附加檢查；不適用則 skip。

有任一 fail，先補讀或修正再進入最終輸出。

## 3. 實際同步

順序：

1. KB 主檔：更新狀態、待辦、日期、下一步。
2. daily 對帳：daily 已由呼叫者寫好；只驗一致，不追加第二筆。
3. 記憶：
   - `read-only`：只檢查與回報，不寫。
   - `update`：依目前平台的 memory policy 更新；Codex 只新增小型 extension note，不直接改 runtime 生成的 `MEMORY.md`／rollout summaries；Claude 只改傳入且確認屬於本專案的 memory files。
4. 開發 repo docs：僅在 dev-mode 命中時處理。

開發 repo 缺根層 README／AGENTS／CLAUDE 說明時：已有可運行程式就補目前平台需要的根文件；仍是 prototype/vibe 階段可跳過，但要在 unresolved 說明。

原則：

- 更新舊條目優於追加；刪除已推翻的臨時結論優於保留。
- 日期一律由 `date` 核實並寫絕對 `YYYY-MM-DD`。
- 主檔不抄 daily 流水帳；actionable todo 不放 daily。
- 同一事實跨檔存在時，用 `rg` 掃引用並對齊。
- 全域 instruction 只有使用者明確表達跨專案原則才改。
- 排課／會議若需改外部系統，只在本次已獲授權時執行；否則列未處理，不能把本地修改冒充完成。
- 發現過去漏同步，只修與本次 scoped/full 審查命中的項目，不順勢擴張到無關 maintenance。

## 4. 最終驗證與回傳

若修改過文件，重跑 enumerate。回傳：

```text
enumeration:
<final enumerate.sh output>

gate: G1-Gn pass; <skip/fail details>
grep: <keyword -> files -> conclusion>
memory: read-only | updated <files> | unchanged
docs:
- <file>: <change>
unresolved:
- <item and reason>
```

只列實際修改與失敗細節；不要重述完整協議。
