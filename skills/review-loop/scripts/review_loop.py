#!/usr/bin/env python3
"""review_loop —— 讓「人審查 AI 寫的長文件」這件事不會在改版之間走樣。

只用 Python 標準函式庫，不需要安裝任何東西。

它在做的事只有一件：讓「實際發生的變更」與「被人看見的變更」數量相等。
飄移的定義就是這兩個數字對不起來——有東西改了、甚至整段不見了，
而審查的人從頭到尾不知道。

三個指令：

  render <doc.md>    把文件渲染成可審查的網頁（每段一個評論格），並記錄這一版的狀態
  check <doc.md>     出版前的閘門。覆蓋率、核可竄改、隱式繼承、重複數字，有問題就非零退出
  apply <doc.md> <feedback.txt>   吃審查回饋，更新每段狀態，印出待辦清單

文件格式：在 markdown 裡用一行註解標出每一段的永久代號。

    <!-- @block intro -->
    ## 這份文件是什麼
    內文……

    <!-- @block timeline -->
    ## 時間軸
    內文……

代號（intro、timeline）出生時取一次，之後**永遠不能改**。
標題可以改、順序可以換、內文可以重寫，代號跟著那塊內容走。
顯示的編號是渲染時自動生成的，不要手寫。

要拿掉一段時，不要直接刪掉——那樣它會從審查流程裡整個消失，
不是被否決，是從來沒進過任何人的視野。改成留一行：

    <!-- @block old-section removed: 併進 timeline 了，這段的判斷已不適用 -->

狀態不用手寫，全部由這支腳本算出來（比對內容雜湊）：

  new        這一版才出現
  edited     內容跟上一版不一樣
  unchanged  內容跟上一版一模一樣
  approved   審查的人核可過，且核可之後沒有再動過
  removed    顯式移除，渲染成灰色仍留在文件裡

狀態記在 <doc>.review-state.json，那個檔是**產物不是原稿**，不要手動編輯。
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

BLOCK_RE = re.compile(
    r"^[ \t]*<!--[ \t]*@block[ \t]+([A-Za-z0-9][A-Za-z0-9_-]*)"
    r"(?:[ \t]+removed[ \t]*:[ \t]*(.*?))?[ \t]*-->[ \t]*$"
)

# 隱式繼承：一段內容如果要靠「參照別段」才看得懂，改版時那個參照會爛掉，
# 而且被參照的那段一旦歸檔，這段就殘廢了。每一段都要能單獨看懂。
INHERIT_PATTERNS = [
    (r"同\s*v\d", "同 vN"),
    (r"同上一?版", "同上一版"),
    (r"同前[一]?[節段版]", "同前節"),
    (r"見前[一]?[節段]", "見前節"),
    (r"可跳過", "可跳過"),
    (r"[（(]?同上[）)]?", "同上"),
    (r"unchanged from v\d", "unchanged from vN"),
    (r"same as (?:above|previous)", "same as above"),
]

NUMBER_RE = re.compile(
    r"(?:NT\$|US\$|\$|USD|TWD)\s?[\d,]+(?:\.\d+)?"       # 金額
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"                  # 帶千分位
    r"|\b\d+\s*(?:分鐘|小時|人|天|週|個月|%)"              # 帶單位
)

STATUS_ORDER = ["new", "edited", "unchanged", "approved", "removed"]
STATUS_LABEL = {
    "new": "新增",
    "edited": "已改",
    "unchanged": "未動",
    "approved": "已核可",
    "removed": "已移除",
}

DEFAULT_MIN_COVERAGE = 1.0  # 上一版的區塊必須 100% 在這一版有下落（在或顯式移除）


# ---------------------------------------------------------------- 解析

def sha(text):
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def first_heading(body):
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:40]
    return ""


def parse(path):
    """讀 markdown，切成區塊。回傳 (preamble, [block,...])。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    blocks, preamble, cur, seen = [], [], None, {}
    for lineno, line in enumerate(lines, 1):
        m = BLOCK_RE.match(line)
        if not m:
            (cur["lines"] if cur else preamble).append(line)
            continue
        bid, removed_reason = m.group(1), m.group(2)
        if bid in seen:
            sys.exit(f"錯誤：區塊代號重複 '{bid}'（第 {seen[bid]} 行與第 {lineno} 行）。"
                     f"\n代號是身分，必須唯一。")
        seen[bid] = lineno
        cur = {"id": bid, "lineno": lineno, "lines": [],
               "removed_reason": (removed_reason or "").strip() or None}
        blocks.append(cur)

    for b in blocks:
        b["body"] = "\n".join(b["lines"]).strip()
        b["hash"] = sha(b["body"])
        b["title"] = b["removed_reason"] and f"（已移除）{b['id']}" or first_heading(b["body"])
    return "\n".join(preamble).strip(), blocks


def state_path(doc):
    return os.path.splitext(doc)[0] + ".review-state.json"


def load_state(doc):
    p = state_path(doc)
    if not os.path.exists(p):
        return {"schema_version": 1, "doc": os.path.basename(doc),
                "current_version": 0, "blocks": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_state(doc, st):
    with open(state_path(doc), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- 狀態計算

def compute(blocks, st, bump=False):
    """比對雜湊算出每個區塊這一版的狀態。bump=True 時把新狀態寫回 state。"""
    prev = st.get("blocks", {})
    version = st.get("current_version", 0) + (1 if bump else 0)
    version = max(version, 1)
    out = []

    for b in blocks:
        rec = prev.get(b["id"])
        if b["removed_reason"]:
            status = "removed"
        elif rec is None:
            status = "new"
        elif rec.get("status") == "removed":
            status = "new"            # 移除之後又加回來，當新的看
        elif rec.get("hash") != b["hash"]:
            status = "edited"
        elif rec.get("approved_hash") == b["hash"]:
            status = "approved"
        else:
            status = "unchanged"

        b["status"] = status
        b["first_seen"] = (rec or {}).get("first_seen", version)
        b["approved_hash"] = (rec or {}).get("approved_hash")
        b["prev_hash"] = (rec or {}).get("hash")
        out.append(b)

    if bump:
        newblocks = {}
        for b in out:
            rec = dict(prev.get(b["id"], {}))
            rec.update({"hash": b["hash"], "status": b["status"],
                        "first_seen": b["first_seen"], "title": b["title"]})
            if b["removed_reason"]:
                rec["removed_reason"] = b["removed_reason"]
            newblocks[b["id"]] = rec
        # 上一版有、這一版整個消失的，強制留下墓碑，不讓它靜靜不見
        for bid, rec in prev.items():
            if bid not in newblocks:
                rec = dict(rec)
                rec["status"] = "vanished"
                newblocks[bid] = rec
        st["blocks"] = newblocks
        st["current_version"] = version
        st["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return version, out


# ---------------------------------------------------------------- 檢查

def coverage(prev_blocks, cur_ids):
    """上一版的區塊，有多少在這一版找得到下落（還在，或顯式標了移除）。

    這是整支腳本最重要的一個數字。用 agent 去「找有沒有漏東西」永遠不可靠，
    改成算一個有分母的比率，少一段就是比率掉下來，不需要有人「注意到」。
    """
    live = [bid for bid, rec in prev_blocks.items() if rec.get("status") != "vanished"]
    if not live:
        return 1.0, [], 0, 0
    missing = [bid for bid in live if bid not in cur_ids]
    matched = len(live) - len(missing)
    return matched / len(live), missing, matched, len(live)


def check(doc, min_cov=DEFAULT_MIN_COVERAGE, strict_numbers=False):
    st = load_state(doc)
    _, blocks = parse(doc)
    version, blocks = compute(blocks, st, bump=False)
    cur_ids = {b["id"] for b in blocks}
    errors, warns = [], []

    # 一、覆蓋率：上一版的東西不准無聲消失
    cov, missing, matched, total = coverage(st.get("blocks", {}), cur_ids)
    if total:
        line = f"覆蓋率 {cov:.3f}（{matched}/{total}，門檻 {min_cov}）"
        if cov < min_cov:
            errors.append(f"{line}\n     上一版有、這一版找不到的區塊：{'、'.join(missing)}"
                          f"\n     要拿掉請留一行 <!-- @block <id> removed: 理由 -->，不要直接刪。")
        else:
            print(f"  ok   {line}")

    # 二、核可過的區塊被改了卻沒說
    tampered = [b for b in blocks
                if b["approved_hash"] and b["hash"] != b["approved_hash"]
                and b["status"] != "removed"]
    if tampered:
        errors.append("核可過的區塊被改動：" + "、".join(b["id"] for b in tampered) +
                      "\n     核可＝那一刻的內容被凍結。要改就要重新送審，不能默默改掉。")
    else:
        napp = sum(1 for b in blocks if b["status"] == "approved")
        print(f"  ok   核可區塊 {napp} 個，內容與核可當下一致")

    # 三、隱式繼承：每一段都要能單獨看懂
    hits = []
    for b in blocks:
        for pat, label in INHERIT_PATTERNS:
            if re.search(pat, b["body"]):
                hits.append(f"{b['id']}（{label}）")
                break
    if hits:
        errors.append("出現指向其他版本或其他段落的寫法：" + "、".join(hits) +
                      "\n     這類參照在改版或歸檔之後會爛掉。每一段都要自己講完整。")
    else:
        print("  ok   沒有隱式繼承的寫法")

    # 四、同一個數字寫在兩個地方（會各自漂成兩套說法）
    where = {}
    for b in blocks:
        if b["status"] == "removed":
            continue
        for n in set(NUMBER_RE.findall(b["body"])):
            where.setdefault(n.strip(), set()).add(b["id"])
        # 忽略純敘述性的小數字，只看有單位或幣別的
    dupes = {n: ids for n, ids in where.items() if len(ids) > 1}
    if dupes:
        msg = "同一個數字出現在多個區塊（兩邊會各自漂）：\n" + "\n".join(
            f"     {n} → {'、'.join(sorted(ids))}" for n, ids in sorted(dupes.items())[:12])
        (errors if strict_numbers else warns).append(msg)
    else:
        print("  ok   沒有重複出現的數字")

    print()
    for w in warns:
        print(f"  注意 {w}")
    for e in errors:
        print(f"  失敗 {e}")
    if errors:
        print(f"\n沒過。{len(errors)} 項要處理。")
        return 1
    print("通過。" + ("（有注意事項，不擋出版）" if warns else ""))
    return 0


# ---------------------------------------------------------------- 渲染

def md_lite(text):
    """把區塊內文轉成夠用的 HTML。刻意不做完整 markdown——這是審查頁不是出版品。"""
    out, in_ul, in_code = [], False, False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        if not line.strip():
            if in_ul:
                out.append("</ul>"); in_ul = False
            continue
        esc = html.escape(line)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"`(.+?)`", r"<code>\1</code>", esc)
        m = re.match(r"^(#{1,6})\s+(.*)$", esc)
        if m:
            if in_ul:
                out.append("</ul>"); in_ul = False
            lvl = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
            continue
        if re.match(r"^\s*[-*]\s+", esc):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + re.sub(r"^\s*[-*]\s+", "", esc) + "</li>")
            continue
        if in_ul:
            out.append("</ul>"); in_ul = False
        out.append(f"<p>{esc}</p>")
    if in_ul:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def render(doc, out_path=None, title=None):
    st = load_state(doc)
    preamble, blocks = parse(doc)
    prev_ids = set(st.get("blocks", {}))
    version, blocks = compute(blocks, st, bump=True)
    cov, missing, matched, total = coverage(
        {k: v for k, v in st["blocks"].items() if k in prev_ids},
        {b["id"] for b in blocks})

    here = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.join(here, "..", "assets", "template.html")
    if not os.path.exists(tpl_path):                       # 腳本被單獨搬走時的退路
        tpl_path = os.path.join(here, "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()

    counts = {s: sum(1 for b in blocks if b["status"] == s) for s in STATUS_ORDER}
    changed = counts["new"] + counts["edited"] + counts["removed"]

    cards = []
    for i, b in enumerate(blocks, 1):
        cards.append(
            '<section class="blk s-{st}" data-id="{id}" data-status="{st}">'
            '<div class="bhead"><span class="num">{i:02d}</span>'
            '<span class="btitle">{title}</span>'
            '<span class="badge">{lab}</span>'
            '<code class="bid">{id}</code></div>'
            '{rm}<div class="body">{body}</div>'
            '<div class="cmt"><div class="intent">'
            '<label><input type="radio" name="i-{id}" value="通過">通過</label>'
            '<label><input type="radio" name="i-{id}" value="改">改</label>'
            '<label><input type="radio" name="i-{id}" value="問">問</label>'
            '<label><input type="radio" name="i-{id}" value="討論">討論</label>'
            '</div><textarea data-for="{id}" rows="2" '
            'placeholder="這一段的意見（不填就等於沒意見）"></textarea></div>'
            '</section>'.format(
                id=html.escape(b["id"]), st=b["status"], i=i,
                title=html.escape(b["title"] or b["id"]),
                lab=STATUS_LABEL[b["status"]],
                rm=('<p class="rmwhy">移除理由：%s</p>' % html.escape(b["removed_reason"]))
                   if b["removed_reason"] else "",
                body=md_lite(b["body"]) if not b["removed_reason"] else ""))

    filled = (tpl
              .replace("{{TITLE}}", html.escape(title or os.path.basename(doc)))
              .replace("{{VERSION}}", str(version))
              .replace("{{PREAMBLE}}", md_lite(preamble) if preamble else "")
              .replace("{{COVERAGE}}", f"{cov:.1%}" if total else "—")
              .replace("{{COVDETAIL}}", f"{matched}/{total}" if total else "第一版")
              .replace("{{CHANGED}}", str(changed))
              .replace("{{TOTAL}}", str(len(blocks)))
              .replace("{{CNEW}}", str(counts["new"]))
              .replace("{{CEDIT}}", str(counts["edited"]))
              .replace("{{CSAME}}", str(counts["unchanged"] + counts["approved"]))
              .replace("{{CREMOVED}}", str(counts["removed"]))
              .replace("{{BLOCKS}}", "\n".join(cards)))

    out_path = out_path or f"{os.path.splitext(doc)[0]}-review-v{version}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(filled)
    save_state(doc, st)

    print(f"第 {version} 版審查頁：{out_path}")
    print(f"  區塊 {len(blocks)}｜新增 {counts['new']}　已改 {counts['edited']}　"
          f"未動 {counts['unchanged'] + counts['approved']}　已移除 {counts['removed']}")
    if total:
        print(f"  覆蓋率 {cov:.1%}（{matched}/{total}）" +
              ("" if not missing else f"　無下落：{'、'.join(missing)}"))
    return 0


# ---------------------------------------------------------------- 回饋

FB_RE = re.compile(r"^\s*\[([A-Za-z0-9][A-Za-z0-9_-]*)\]\s*(通過|改|問|討論)\s*(?:[—\-–:：]\s*(.*))?$")


def apply_fb(doc, fb_path):
    st = load_state(doc)
    _, blocks = parse(doc)
    compute(blocks, st, bump=False)
    byid = {b["id"]: b for b in blocks}

    with open(fb_path, encoding="utf-8") as f:
        raw = f.read()

    items, unknown = [], []
    for line in raw.splitlines():
        m = FB_RE.match(line)
        if not m:
            continue
        bid, intent, note = m.group(1), m.group(2), (m.group(3) or "").strip()
        if bid not in byid:
            unknown.append(bid)
            continue
        items.append({"id": bid, "intent": intent, "note": note})

    if not items:
        sys.exit("回饋檔裡沒有解析到任何一行。格式是：[區塊代號] 通過|改|問|討論 — 意見")

    for it in items:
        rec = st["blocks"].setdefault(it["id"], {})
        if it["intent"] == "通過":
            rec["approved_hash"] = byid[it["id"]]["hash"]
            rec["approved_at_version"] = st.get("current_version")
            rec["status"] = "approved"
        rec["last_intent"] = it["intent"]
        if it["note"]:
            rec["last_note"] = it["note"]
    save_state(doc, st)

    todo = [i for i in items if i["intent"] != "通過"]
    passed = [i for i in items if i["intent"] == "通過"]

    print(f"收到 {len(items)} 條回饋。通過 {len(passed)}，要處理 {len(todo)}。")
    if unknown:
        print(f"注意：代號不存在，已略過 → {'、'.join(unknown)}")
    if passed:
        print(f"\n已凍結（之後改動會被 check 擋下）：{'、'.join(i['id'] for i in passed)}")
    if todo:
        print("\n待辦：")
        for i in todo:
            print(f"  [{i['id']}] {i['intent']}　{i['note'] or '（沒寫理由，先去問清楚再動手）'}")
    silent = [b["id"] for b in blocks
              if b["status"] in ("new", "edited") and b["id"] not in {i["id"] for i in items}]
    if silent:
        print(f"\n這些區塊這一版改過、但沒有收到任何回饋，別當作默認通過：{'、'.join(silent)}")
    return 0


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(
        description="讓長文件的多輪審查不會在改版之間走樣",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="渲染審查頁，並記錄這一版")
    r.add_argument("doc"); r.add_argument("-o", "--out"); r.add_argument("-t", "--title")

    c = sub.add_parser("check", help="出版前閘門，有問題就非零退出")
    c.add_argument("doc")
    c.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    c.add_argument("--strict-numbers", action="store_true",
                   help="把「同一個數字出現在多個區塊」也當成失敗")

    a = sub.add_parser("apply", help="吃審查回饋，更新狀態並印待辦")
    a.add_argument("doc"); a.add_argument("feedback")

    args = ap.parse_args()
    if not os.path.exists(args.doc):
        sys.exit(f"找不到檔案：{args.doc}")

    if args.cmd == "render":
        return render(args.doc, args.out, args.title)
    if args.cmd == "check":
        print(f"檢查 {args.doc}")
        return check(args.doc, args.min_coverage, args.strict_numbers)
    if args.cmd == "apply":
        return apply_fb(args.doc, args.feedback)


if __name__ == "__main__":
    sys.exit(main())
