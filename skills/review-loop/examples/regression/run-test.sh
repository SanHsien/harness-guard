#!/usr/bin/env bash
# 回歸測試：用一份真實案例的三個版本，證明這套東西抓得到當初漏掉的三種飄移。
#
# 測資是一份虛構的社區工具圖書館籌備規格，但三種失敗都是照著一次真實事故複製的。
# 那次是一份長規格做了四輪審查，當時沒有這套工具，結果：
#   1. 一整章在改版之間消失，沒有人發現——連事後派去做版本比對的
#      獨立 AI 審核也沒抓到，它只找到 9 個較小的遺漏。
#   2. 章節編號全面位移，v1 的「第 4 章」與 v2 的「第 4 章」是完全不同的內容。
#   3. 一個已經被口頭核可（「01: PASS」）的章節，事後被改了標題、插入新小節、
#      重新編號，核可的人從頭到尾不知道。
#
# 三個都應該被擋下來。擋不下來就是這套工具沒做到它宣稱的事。

set -u
cd "$(dirname "$0")"
RL="python3 ../../scripts/review_loop.py"
pass=0; fail=0

ok()   { echo "  通過  ${1}"; pass=$((pass+1)); }
bad()  { echo "  失敗  ${1}"; fail=$((fail+1)); }
step() { echo; echo "── $1"; }

rm -f spec.md spec.review-state.json spec-review-v*.html feedback.txt

step "第 1 版：九章，第一次渲染"
cp v1.md spec.md
$RL render spec.md -o spec-review-v1.html >/dev/null 2>&1 \
  && ok "渲染成功" || bad "渲染失敗"
grep -q '"first-principles"' spec.review-state.json \
  && ok "第一性原理那章已登記在案" || bad "沒登記到"

step "第 2 版：模擬當初的真實情況——整章直接刪掉，什麼都沒說"
cp v2.md spec.md
out=$($RL check spec.md 2>&1); rc=$?
echo "$out" | sed 's/^/     /'
if [ $rc -ne 0 ]; then ok "擋下來了（覆蓋率不足）"; else bad "沒擋住，這是最該抓到的一條"; fi
echo "$out" | grep -q "first-principles" \
  && ok "指名了消失的是哪一章" || bad "沒指名是哪一章，人還是不知道要看什麼"

step "第 3 版：照規矩留下墓碑，宣告這兩章被拿掉了"
cp v2.md spec.md
cat >> spec.md <<'EOF'

<!-- @block first-principles removed: 刪除測試的結論已落進 trial 與 inventory，不再獨立成章 -->

<!-- @block shape removed: 併進 process，借還兩件事的骨架已寫在流程那節 -->
EOF
out=$($RL check spec.md 2>&1)
if echo "$out" | grep -q "ok   覆蓋率 1.000"; then
  ok "宣告之後覆蓋率回到 100%（工具不是在阻止你刪東西，是要你講出來）"
else echo "$out" | sed 's/^/     /'; bad "宣告了覆蓋率還是不足，判斷邏輯有問題"; fi
$RL render spec.md -o spec-review-v2.html >/dev/null 2>&1
grep -q "已移除" spec-review-v2.html \
  && ok "移除的章節仍留在審查頁上（灰掉、刪除線）" || bad "移除的章節沒有留在頁面上"

step "第 4 版：審查的人核可了 trial 這一章"
cat > feedback.txt <<'EOF'
## 審查回饋
[trial] 通過
[space] 改 — 三區改成兩區就好
[materials] 通過
EOF
$RL apply spec.md feedback.txt 2>&1 | sed 's/^/     /'
python3 -c "
import json;d=json.load(open('spec.review-state.json'))
import sys;sys.exit(0 if d['blocks']['trial'].get('approved_hash') else 1)" \
  && ok "核可被凍結成雜湊" || bad "核可沒被記錄"

step "第 5 版：核可過的那一章被偷偷改掉（當初真的發生的事）"
cp v3.md spec.md
cat >> spec.md <<'EOF'

<!-- @block first-principles removed: 刪除測試的結論已落進 trial 與 inventory，不再獨立成章 -->

<!-- @block shape removed: 併進 process，借還兩件事的骨架已寫在流程那節 -->
EOF
out=$($RL check spec.md 2>&1); rc=$?
echo "$out" | sed 's/^/     /'
if [ $rc -ne 0 ]; then ok "擋下來了"; else bad "沒擋住，核可等於沒用"; fi
echo "$out" | grep -q "核可過的區塊被改動" \
  && ok "講清楚是核可竄改，不是普通的改動" || bad "沒講清楚是哪一類問題"

step "額外：隱式繼承的寫法"
cp v1.md spec2.md
cat >> spec2.md <<'EOF'

<!-- @block pointer-bug -->
## 教具來源
本節同 v2，可跳過。
EOF
rm -f spec2.review-state.json
$RL render spec2.md -o /dev/null >/dev/null 2>&1
out=$($RL check spec2.md 2>&1)
echo "$out" | grep -q "隱式繼承\|指向其他版本" \
  && ok "抓到「同 v2，可跳過」這種會爛掉的寫法" || bad "沒抓到隱式繼承"

echo
echo "────────────────────────────"
echo "通過 ${pass}　失敗 ${fail}"
rm -f spec.md spec2.md spec*.review-state.json spec-review-v*.html feedback.txt
[ $fail -eq 0 ] || exit 1
