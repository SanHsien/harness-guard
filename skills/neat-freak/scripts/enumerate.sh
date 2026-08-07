#!/bin/bash
# neat-freak 第一步機械枚舉腳本 — 產出不可偽造的盤點證據。
# 用法：enumerate.sh [--memory <memory-dir>] [--vault <kb-root>] [<project-root> ...]
# --vault：知識庫對帳（daily↔主檔 ✅ 對照、缺 tag、假日期、跨檔重複待辦）
# --memory：記憶健檢（broken index links、相對時間）
# <project-root>：開發 repo 才傳（docs/README 枚舉）
# 輸出直接原樣貼進最終摘要的「第一步盤點證據」段，不得手打或改寫數字。
set -uo pipefail

MEMORY_DIR=""
VAULT=""
ROOTS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --memory) MEMORY_DIR="${2:-}"; shift 2 ;;
    --vault) VAULT="${2:-}"; shift 2 ;;
    *) ROOTS+=("$1"); shift ;;
  esac
done

# 以下兩個 pattern 依你自己的待辦格式調整，或用環境變數覆寫。
REL_TIME_PATTERN="${REL_TIME_PATTERN:-今天|昨天|剛剛|最近|上週|上周|today|yesterday|recently}"
# 你的待辦分類 tag；沒有 tag 體系就設成一個不會命中的字串以跳過該檢查。
TAG_PATTERN="${TAG_PATTERN:-#(work|life|admin)}"
TODAY=$(date '+%Y-%m-%d')

echo "=== neat-freak enumeration @ $(date '+%Y-%m-%d %H:%M %z') ==="

if [[ -n "$MEMORY_DIR" ]]; then
  if [[ -d "$MEMORY_DIR" ]]; then
    echo "--- memory: $MEMORY_DIR ---"
    md_count=$(find "$MEMORY_DIR" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
    echo "md files: $md_count"
    for t in user feedback project reference; do
      c=$(grep -l "type: $t" "$MEMORY_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
      echo "  type=$t: $c"
    done
    if [[ -f "$MEMORY_DIR/MEMORY.md" ]]; then
      echo "MEMORY.md lines: $(wc -l < "$MEMORY_DIR/MEMORY.md" | tr -d ' ')"
      broken=0
      while IFS= read -r f; do
        if [[ ! -f "$MEMORY_DIR/$f" ]]; then
          echo "  BROKEN index link: $f"
          broken=$((broken + 1))
        fi
      done < <(grep -o '([A-Za-z0-9_.-]*\.md)' "$MEMORY_DIR/MEMORY.md" | tr -d '()' | sort -u)
      echo "broken index links: $broken"
    else
      echo "MEMORY.md: MISSING"
    fi
    rel=$(grep -rEc "$REL_TIME_PATTERN" "$MEMORY_DIR"/*.md 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
    echo "relative-time hits in memory: $rel"
    [[ "$rel" -gt 0 ]] && grep -rEn "$REL_TIME_PATTERN" "$MEMORY_DIR"/*.md 2>/dev/null | head -10
  else
    echo "--- memory: $MEMORY_DIR --- NOT FOUND"
  fi
fi

if [[ -n "$VAULT" ]]; then
  if [[ -d "$VAULT" ]]; then
    echo "--- vault: $VAULT ---"
    MAIN_DIRS=()
    # 你的知識庫「主檔」資料夾；用 VAULT_MAIN_DIRS 覆寫（空白分隔）。不存在的自動略過。
    for d in ${VAULT_MAIN_DIRS:-pillars projects decisions personal notes}; do
      [[ -d "$VAULT/$d" ]] && MAIN_DIRS+=("$VAULT/$d")
    done

    # 1. daily ↔ 主檔 ✅ 對照（啟發式：兩邊數字說不通就逐條查）
    daily_file="$VAULT/daily/$TODAY.md"
    if [[ -f "$daily_file" ]]; then
      echo "daily note today: daily/$TODAY.md"
      echo "  '✅ $TODAY' in daily note: $(grep -c "✅ $TODAY" "$daily_file" 2>/dev/null)"
    else
      latest=$(ls "$VAULT/daily" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$' | sort | tail -1)
      echo "daily note today: MISSING (daily/$TODAY.md; latest = ${latest:-none})"
    fi
    done_main=$(grep -rc --include='*.md' "✅ $TODAY" "${MAIN_DIRS[@]}" 2>/dev/null | awk -F: '{s+=$NF} END {print s+0}')
    echo "'✅ $TODAY' in 主檔 (${VAULT_MAIN_DIRS:-預設資料夾}): $done_main"

    # 2. 開放待辦缺分類 tag（見檔頭 TAG_PATTERN）
    miss=$(grep -rn --include='*.md' '^- \[ \]' "${MAIN_DIRS[@]}" 2>/dev/null | grep -v '_TEMPLATE' | grep -Ev "$TAG_PATTERN" | wc -l | tr -d ' ')
    echo "open todos missing tag: $miss"
    [[ "$miss" -gt 0 ]] && grep -rn --include='*.md' '^- \[ \]' "${MAIN_DIRS[@]}" 2>/dev/null | grep -v '_TEMPLATE' | grep -Ev "$TAG_PATTERN" | sed "s|$VAULT/||" | head -10

    # 3. 假日期（📅 後面不是 YYYY-）
    fake=$(grep -rEn --include='*.md' '📅 *[^0-9 ]' "${MAIN_DIRS[@]}" 2>/dev/null | grep -v '_TEMPLATE' | wc -l | tr -d ' ')
    echo "fake dates (📅 followed by non-date): $fake"
    [[ "$fake" -gt 0 ]] && grep -rEn --include='*.md' '📅 *[^0-9 ]' "${MAIN_DIRS[@]}" 2>/dev/null | grep -v '_TEMPLATE' | sed "s|$VAULT/||" | head -10

    # 4. 跨檔重複開放待辦（SSOT 違規：同一任務文字活在兩個檔）
    dup=$(grep -rh --include='*.md' --exclude='_TEMPLATE.md' '^- \[ \]' "${MAIN_DIRS[@]}" 2>/dev/null \
      | sed -E 's/^- \[ \] +//; s/ *📅 [0-9-]+//; s/ *#[^ ]+//g; s/ +$//' \
      | grep -v '〈' | grep -v '^$' | LC_ALL=C sort | LC_ALL=C uniq -d)
    if [[ -n "$dup" ]]; then
      echo "duplicate open todos (normalized text, cross-file): $(printf '%s\n' "$dup" | wc -l | tr -d ' ')"
      printf '%s\n' "$dup" | head -5 | sed 's/^/  DUP: /'
    else
      echo "duplicate open todos (normalized text, cross-file): 0"
    fi

    # 5. 主檔相對時間 — 只掃開放待辦行與狀態行（進度日誌引述對話的「今天」是歷史記錄，不算）
    rel=$(grep -rEn --include='*.md' '^(- \[[ /]\]|> \*\*狀態)' "${MAIN_DIRS[@]}" 2>/dev/null | grep -Ec "$REL_TIME_PATTERN")
    echo "relative-time hits in 主檔 todo/狀態行: $rel"
    [[ "$rel" -gt 0 ]] && grep -rEn --include='*.md' '^(- \[[ /]\]|> \*\*狀態)' "${MAIN_DIRS[@]}" 2>/dev/null | grep -E "$REL_TIME_PATTERN" | sed "s|$VAULT/||" | head -10

    # 6. 知識庫根目錄誤生的日期空檔（日誌工具設錯路徑時會在這裡留下空檔）
    stray=$(ls "$VAULT" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$' | wc -l | tr -d ' ')
    echo "stray date-named md at vault root: $stray"
    [[ "$stray" -gt 0 ]] && ls "$VAULT" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$' | sed 's/^/  STRAY: /'
  else
    echo "--- vault: $VAULT --- NOT FOUND"
  fi
fi

for ROOT in "${ROOTS[@]+"${ROOTS[@]}"}"; do
  if [[ ! -d "$ROOT" ]]; then
    echo "--- project: $ROOT --- NOT FOUND"
    continue
  fi
  echo "--- project: $ROOT ---"
  echo "root entries: $(ls "$ROOT" | wc -l | tr -d ' ')"
  echo "root md files:"
  find "$ROOT" -maxdepth 1 -name '*.md' -exec basename {} \; | sed 's/^/  /'
  if [[ -d "$ROOT/docs" ]]; then
    echo "docs/ md files: $(find "$ROOT/docs" -name '*.md' | wc -l | tr -d ' ')"
    find "$ROOT/docs" -name '*.md' | sed "s|$ROOT/||; s/^/  /"
  else
    echo "docs/: 不存在"
  fi
  if [[ -d "$ROOT/.claude/rules" ]]; then
    echo ".claude/rules/ md files: $(find "$ROOT/.claude/rules" -name '*.md' | wc -l | tr -d ' ')"
  else
    echo ".claude/rules/: 不存在"
  fi
  if [[ -d "$ROOT/.claude/skills" ]]; then
    echo ".claude/skills/ dirs: $(find "$ROOT/.claude/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
  fi
  echo "md files (maxdepth 2, excl node_modules/.git): $(find "$ROOT" -maxdepth 2 -name '*.md' -not -path '*/node_modules/*' -not -path '*/.git/*' | wc -l | tr -d ' ')"
  rel=0
  for f in "$ROOT/README.md" "$ROOT/CLAUDE.md" "$ROOT/AGENTS.md"; do
    [[ -f "$f" ]] && rel=$((rel + $(grep -Ec "$REL_TIME_PATTERN" "$f" || true)))
  done
  if [[ -d "$ROOT/docs" ]]; then
    d=$(grep -rEc "$REL_TIME_PATTERN" "$ROOT/docs" --include='*.md' 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
    rel=$((rel + d))
  fi
  echo "relative-time hits in README/CLAUDE/AGENTS/docs: $rel"
done

echo "=== enumeration end ==="
