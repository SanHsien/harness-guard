# Agent 記憶與配置路徑速查

不同 agent 平台的記憶系統和專案配置文件位置不一樣。執行第一步盤點時按你正在使用的平台查這張表。

## Claude Code

| 用途 | 路徑 |
|---|---|
| 跨會話記憶（全域） | `~/.claude/projects/<encoded-project-path>/memory/` |
| 記憶索引文件 | `~/.claude/projects/<...>/memory/MEMORY.md` |
| 全域指令 | `~/.claude/CLAUDE.md` |
| 專案級指令 | 專案根 `CLAUDE.md`（可層級嵌套） |
| Skills 目錄 | `~/.claude/skills/<name>/SKILL.md` |

記憶文件用 YAML frontmatter：`name`、`description`、`type`（user / feedback / project / reference）。

## OpenAI Codex

| 用途 | 路徑 |
|---|---|
| 跨會話指令（全域） | `~/.codex/AGENTS.md` 或 `$CODEX_HOME/AGENTS.md` |
| 專案級指令 | 專案根 `AGENTS.md`（可層級嵌套） |
| 專案級 override | `AGENTS.override.md`（若存在，覆蓋同目錄 AGENTS.md） |
| Skills 目錄 | `~/.agents/skills/<name>/SKILL.md` 或專案內 `.agents/skills/<name>/` |

Codex 沒有獨立的「記憶文件 + 索引」機制，所有跨會話資訊都直接寫在 `AGENTS.md` 裡。同步時把「專案事實」那部分內容統一放 AGENTS.md。

發現專案裡有 `TEAM_GUIDE.md` 或 `.agents.md` 也要看——這是 Codex 的 fallback 檔名。

## OpenClaw

| 用途 | 路徑 |
|---|---|
| 使用者級 skills | `~/.openclaw/skills/<name>/SKILL.md`（首次執行自動建立） |
| 專案級 skills | `.openclaw/skills/<name>/SKILL.md`（倉庫根目錄下） |
| Workspace skills | 當前 workspace 的 `skills/` 目錄 |

**載入優先級**：workspace > project-agent > personal-agent > managed/local > bundled > extra dirs。同名 skill 高優先級覆蓋低優先級。

OpenClaw 沒有獨立的「記憶文件 + 索引」機制，跨會話資訊可放在專案根的 markdown（CLAUDE.md / AGENTS.md / 等價文件）裡，參照 Codex 的做法。frontmatter 支援 `metadata.openclaw` 欄位做載入時的 gating（按 OS、環境變數、二進位相依篩選），但不是 neat-freak 必需的。

## OpenCode

| 用途 | 路徑 |
|---|---|
| 全域配置 | `~/.config/opencode/` |
| 專案配置 | `.opencode/` |
| Skills 目錄（專案） | `.opencode/skills/`、`.claude/skills/`、`.codex/skills/` 都會被掃描 |
| Skills 目錄（全域） | `~/.config/opencode/skills/`、`~/.claude/skills/`、`~/.codex/skills/` |

OpenCode 同時讀取 Claude Code 和 Codex 的目錄，所以同一個 skill 裝在 `~/.claude/skills/` 下的話三家都能識別。OpenClaw 走自己的 `~/.openclaw/skills/`，需要單獨裝一份（或用符號連結）。

## 如果當前 agent 沒有獨立記憶系統

跳過「記憶」那一層，把功夫全花在：
- 專案根 markdown（CLAUDE.md / AGENTS.md / 本平台等價文件）
- README.md
- docs/

仍然是有效的同步——記憶是錦上添花，docs 才是專案知識的最低保障。

## 跨平台共存策略

如果一個專案同時被 Claude Code 使用者和 Codex 使用者使用，推薦：

- **專案根同時放 `CLAUDE.md` 和 `AGENTS.md`**，內容可以互相 symlink 或在兩邊維護
- 或者一份內容主文件 + 另一份用一行 `See CLAUDE.md` 跳轉
- docs/ 和 README 是平台中立的，不需要分兩份
