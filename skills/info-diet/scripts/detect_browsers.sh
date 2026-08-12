#!/usr/bin/env bash
# detect_browsers.sh — 找出使用者實際在用的瀏覽器 profile
#
# 重要：這支腳本「只看檔案的大小與修改時間」，不會打開、不會讀取任何一筆瀏覽紀錄。
# 它的唯一產出是一張候選清單，外加一行複製指令。
#
# 為什麼不直接讀？兩個原因：
#   1. Chrome 執行中會鎖住 History 檔，直接讀會拿到不完整或鎖死的資料。
#   2. 讀瀏覽紀錄會碰到權限守衛。多數設定是跳出詢問（使用者按同意即可），
#      但嚴格設定（例如 auto 模式的分類器）會直接硬擋、連問都不問——
#      實測遇過。所以流程要能兩邊都走：先由 AI 執行複製，被擋就改請使用者自己跑。
#
# 用法：bash detect_browsers.sh [輸出目錄]
#   輸出目錄預設 ~/.info-diet/

set -uo pipefail

OUTDIR="${1:-$HOME/.info-diet}"

echo "=== 正在尋找瀏覽器（只看檔案大小與時間，不讀內容）==="
echo

# Chromium 家族：schema 完全相同，一套解析程式全部吃得下
# 格式：顯示名稱|使用者資料根目錄
CHROMIUM_ROOTS=(
  "Chrome|$HOME/Library/Application Support/Google/Chrome"
  "Chrome Beta|$HOME/Library/Application Support/Google/Chrome Beta"
  "Chrome Canary|$HOME/Library/Application Support/Google/Chrome Canary"
  "Edge|$HOME/Library/Application Support/Microsoft Edge"
  "Brave|$HOME/Library/Application Support/BraveSoftware/Brave-Browser"
  "Vivaldi|$HOME/Library/Application Support/Vivaldi"
  "Arc|$HOME/Library/Application Support/Arc/User Data"
  "Opera|$HOME/Library/Application Support/com.operasoftware.Opera"
  "Chrome (Linux)|$HOME/.config/google-chrome"
  "Chromium (Linux)|$HOME/.config/chromium"
  "Brave (Linux)|$HOME/.config/BraveSoftware/Brave-Browser"
  "Edge (Linux)|$HOME/.config/microsoft-edge"
)

TMP_LIST="$(mktemp)"
trap 'rm -f "$TMP_LIST"' EXIT

for entry in "${CHROMIUM_ROOTS[@]}"; do
  name="${entry%%|*}"
  root="${entry#*|}"
  [ -d "$root" ] || continue
  # Chromium 的 profile 一定是 root 底下第一層的資料夾，裡面有一個叫 History 的檔
  while IFS= read -r -d '' hist; do
    prof="$(basename "$(dirname "$hist")")"
    # 用 stat 取「位元組大小」與「修改時間 epoch」，macOS 與 Linux 語法不同
    if stat -f '%z %m' "$hist" >/dev/null 2>&1; then
      read -r bytes mtime <<<"$(stat -f '%z %m' "$hist")"      # macOS / BSD
    else
      read -r bytes mtime <<<"$(stat -c '%s %Y' "$hist")"      # Linux / GNU
    fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$mtime" "$bytes" "$name" "$prof" "$hist" >>"$TMP_LIST"
  done < <(find "$root" -maxdepth 2 -name History -type f -print0 2>/dev/null)
done

if [ ! -s "$TMP_LIST" ]; then
  echo "找不到任何 Chromium 系瀏覽器（Chrome / Edge / Brave / Arc / Vivaldi）的紀錄檔。"
  echo
  echo "STATUS=none"
  exit 0
fi

# 排序決定我們推薦哪一個，所以判準要挑對：
#   - 只看時間：今天不小心點開過的空殼 profile 會排到第一，蓋掉真正的主力。
#   - 只看大小：幾年前用很兇、現在早就不用的舊 profile 會排到第一。
# 所以用「近 45 天內有動過」當及格線，及格的裡面再比大小；
# 全部都沒動過時才退回純比大小。
# 踩過的坑：Default 常常是空殼，真正在用的是 Profile 1 之類的，絕不能寫死 Default。
NOW_EPOCH="$(date +%s)"
RECENT_CUTOFF=$((NOW_EPOCH - 45 * 86400))

awk -F'\t' -v cut="$RECENT_CUTOFF" '{ print (($1 >= cut) ? 1 : 0) "\t" $0 }' "$TMP_LIST" \
  | sort -k1,1nr -k3,3nr -k2,2nr \
  | cut -f2- >"$TMP_LIST.sorted"
mv "$TMP_LIST.sorted" "$TMP_LIST"

echo "找到這些瀏覽器帳號（profile），最可能是主力的排在前面："
echo
printf '   %-16s %-12s %10s   %s\n' "瀏覽器" "帳號" "資料量" "最後使用"
printf '   %s\n' "--------------------------------------------------------------------"

i=0
BEST_PATH=""
BEST_DESC=""
while IFS=$'\t' read -r mtime bytes name prof path; do
  i=$((i + 1))
  # 人看得懂的大小
  if [ "$bytes" -ge 1048576 ]; then
    human="$((bytes / 1048576)) MB"
  else
    human="$((bytes / 1024)) KB"
  fi
  if date -r "$mtime" '+%Y-%m-%d %H:%M' >/dev/null 2>&1; then
    when="$(date -r "$mtime" '+%Y-%m-%d %H:%M')"          # macOS / BSD
  else
    when="$(date -d "@$mtime" '+%Y-%m-%d %H:%M')"         # Linux / GNU
  fi
  mark="  "
  if [ "$i" -eq 1 ]; then
    mark="->"
    BEST_PATH="$path"
    BEST_DESC="$name / $prof"
  fi
  printf ' %s %-16s %-12s %10s   %s\n' "$mark" "$name" "$prof" "$human" "$when"
done <"$TMP_LIST"

echo
echo "箭頭指的是最近才在用、資料也最多的那個，通常就是本人的主力帳號。"
echo "（注意：叫 Default 的不一定是在用的那個，很多人的主力其實是 Profile 1。）"
echo

# 其他瀏覽器：這版不支援，但要明講，不能讓使用者以為掃過了
OTHERS=""
[ -f "$HOME/Library/Safari/History.db" ] && OTHERS="${OTHERS}Safari "
if find "$HOME/Library/Application Support/Firefox/Profiles" -maxdepth 2 -name places.sqlite -print -quit 2>/dev/null | grep -q . ; then
  OTHERS="${OTHERS}Firefox "
fi
if [ -n "$OTHERS" ]; then
  echo "另外偵測到：$OTHERS"
  echo "這一版還不支援它們（資料格式不一樣，Safari 另外還需要「完全取用磁碟」權限）。"
  echo "如果上面那些 Chromium 系的資料量看起來太少，代表主力可能在這裡，那這次的結果會失真。"
  echo
fi

mkdir -p "$OUTDIR"
echo "=== 下一步：把紀錄複製一份出來（Chrome 開著時原檔是鎖住的）==="
echo
echo "cp \"$BEST_PATH\" \"$OUTDIR/history.db\""
echo
echo "先跟使用者說一聲再執行。多數人會跳出確認視窗，按同意即可。"
echo "若被權限設定直接擋下，改請使用者在輸入框用 ! 開頭自己跑這行。"
echo

echo "BEST_PATH=$BEST_PATH"
echo "BEST_DESC=$BEST_DESC"
echo "OUTDIR=$OUTDIR"
echo "STATUS=ok"
