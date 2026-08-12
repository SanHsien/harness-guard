#!/usr/bin/env python3
"""
compare.py — 跟上一次的基準值比對，只吐五個數字。

刻意做得很小。第一次盤點的價值來自「第一次看到自己的數字」，
第二次之後的價值只剩「有沒有動」——所以複驗不需要再產一份長報告，
五行就夠了。長報告反而會讓人懶得跑第二次。

用法：
  python3 compare.py --old ~/.info-diet/baseline-2026-08-12.json \
                     --new ~/.info-diet/baseline-2026-09-12.json
"""

import argparse
import json
import os
import sys


def pct(part, whole):
    return (part / whole * 100) if whole else 0.0


# 刻意「不」判斷方向。
#
# 第一版把五個指標全部設成「下降＝改善」，包含「外部攝取佔比」與「每日平均造訪」。
# 那等於偷渡了「看越少越好」這個價值判斷，而那正是 information diet 原作
# （Clay Johnson）開宗明義反對的框架——他說問題不是量，是選擇；
# 也直接打臉這支工具自己寫的「乾淨型要誠實給」「單一深井不必然是壞事」。
#
# 這是體重計，不是健身教練。體重計只報數字。
# 哪個方向叫進步，是使用者自己在對話裡決定的事。
FLAT_BAND = 1.0   # 一個百分點以內視為沒動；月間雜訊不該被講成「改善」


def moved(delta, unit):
    if unit == "%":
        return "持平" if abs(delta) < FLAT_BAND else f"{delta:+.1f} 個百分點"
    return "持平" if abs(delta) < 5 else f"{delta:+.0f} 次"


def load(path):
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        print(f"找不到基準值檔案：{p}", file=sys.stderr)
        print("STATUS=nofile")
        sys.exit(1)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="上一次的 baseline JSON")
    ap.add_argument("--new", required=True, help="這一次的 baseline JSON")
    args = ap.parse_args()

    a, b = load(args.old), load(args.new)

    if a.get("window_days") != b.get("window_days"):
        print(f"注意：兩次的統計天數不一樣（{a.get('window_days')} 天 vs "
              f"{b.get('window_days')} 天），比出來的差距會失真。")
        print()

    ta, tb = a["total_visits"], b["total_visits"]

    def bucket_pct(d, name):
        return pct(d.get("buckets", {}).get(name, 0), d["total_visits"])

    def feed_pct(d):
        known = d.get("feed_visits", 0) + d.get("detail_visits", 0)
        return pct(d.get("feed_visits", 0), known)

    metrics = [
        ("看自己佔比", bucket_pct(a, "self"), bucket_pct(b, "self"), "%"),
        ("外部攝取佔比", bucket_pct(a, "consume"), bucket_pct(b, "consume"), "%"),
        ("只滑不點的比例", feed_pct(a), feed_pct(b), "%"),
        ("凌晨 00-05 佔比", pct(a.get("late_night_visits", 0), ta),
         pct(b.get("late_night_visits", 0), tb), "%"),
        ("每日平均造訪", ta / max(a.get("days_covered", 1), 1),
         tb / max(b.get("days_covered", 1), 1), "次"),
    ]

    print("=" * 60)
    print(f"資訊飲食複驗　{a['generated_at'][:10]}  ->  {b['generated_at'][:10]}")
    print("=" * 60)
    for name, old, new, unit in metrics:
        if unit == "%":
            line = f"  {name:<16}{old:5.1f}% -> {new:5.1f}%"
        else:
            line = f"  {name:<16}{old:5.0f}{unit} -> {new:5.0f}{unit}"
        print(f"{line:<44}{moved(new - old, unit)}")
    print()
    print("這裡只報數字，不判好壞。")
    print("哪個方向對你叫進步，要看你上次替自己訂的是什麼——")
    print("數字變小不一定是好事，變大也不一定是壞事。")
    print("STATUS=ok")


if __name__ == "__main__":
    main()
