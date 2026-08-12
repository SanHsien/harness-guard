#!/usr/bin/env python3
"""
redact.py — 依使用者指名的關鍵字，從報告裡刪掉整行。

存在的理由：讓使用者「指揮 AI 刪」，而不是「自己開檔案刪」。
零技術背景的人不一定有辦法開檔、找行、存檔——但他一定講得出
「不要有跟醫院有關的」或「把某某網站拿掉」。

**這支腳本的輸出絕對不含被刪掉的內容。** 它只回報刪了幾行、命中哪幾個關鍵字。
所以 AI 可以在完全沒看過報告的情況下執行刪除，然後才第一次讀那份報告。
這是整個隱私承諾能夠成立的關鍵——承諾由流程保證，不是靠 AI 自律。

用法：
  python3 redact.py --report ~/.info-diet/report.txt --terms "醫院,求職,某某網站"
  python3 redact.py --report ... --terms "..." --dry-run    # 只看會刪幾行，不動檔案
"""

import argparse
import os
import shutil
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="要處理的報告檔")
    ap.add_argument("--terms", required=True,
                    help="使用者指名要拿掉的關鍵字，逗號分隔。不分大小寫。")
    ap.add_argument("--dry-run", action="store_true",
                    help="只回報會刪幾行，不真的改檔案")
    args = ap.parse_args()

    path = os.path.expanduser(args.report)
    if not os.path.exists(path):
        print(f"找不到報告檔：{path}", file=sys.stderr)
        print("STATUS=nofile")
        return 1

    terms = [t.strip().lower() for t in args.terms.split(",") if t.strip()]
    if not terms:
        print("沒有給任何關鍵字，沒事可做。")
        print("STATUS=noterms")
        return 0

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    kept, removed_by = [], {t: 0 for t in terms}
    for line in lines:
        low = line.lower()
        hit = next((t for t in terms if t in low), None)
        if hit:
            removed_by[hit] += 1
        else:
            kept.append(line)

    total_removed = len(lines) - len(kept)

    # 只講數量，不講內容。這一行是這支腳本的重點。
    print(f"指定的關鍵字：{len(terms)} 個")
    for t in terms:
        print(f"  「{t}」命中 {removed_by[t]} 行")
    print(f"合計刪除 {total_removed} 行，報告從 {len(lines)} 行剩下 {len(kept)} 行。")
    print("（刪掉的內容沒有印在這裡，也不會出現在任何地方。）")

    if args.dry_run:
        print("這次是試算，檔案沒有被改。")
        print("STATUS=dryrun")
        return 0

    if total_removed:
        shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(kept)
        # 備份檔含有剛剛刪掉的內容，留著等於沒刪，直接移除。
        os.remove(path + ".bak")

    print("STATUS=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
