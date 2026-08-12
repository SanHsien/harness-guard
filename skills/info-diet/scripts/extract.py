#!/usr/bin/env python3
"""
extract.py — 把瀏覽紀錄聚合成「可以交給 AI 看」的統計資料。

隱私設計（這是這支腳本存在的理由，不是附加功能）：
  - 完整網址「絕對不會」出現在輸出裡。網址在記憶體裡用完就丟。
  - 輸出只有三種東西：網域、路徑型態（去掉所有 ID 與參數）、次數與時間。
  - 搜尋關鍵字預設「不」輸出（那是全部資料裡最能還原一個人處境的東西）。
    真的要看得自己加 --with-search，而且會單獨標示出來讓使用者決定要不要給。

實測校正過的兩件事（別改回去）：
  1. 分類必須「按每一次造訪」算，不能按網域算。
     同一個網域會同時是「看自己」跟「外部攝取」——例如 Threads 的
     /activity 是看通知、/ 是看動態。按網域多數決會把整個發現埋掉。
  2. Chrome 的 visit_duration 不能當停留時間用。
     它把「分頁開著但人不在」也算進去，實測加總遠超過一天 24 小時。
     所以這支腳本只用「次數」與「有活動的天數」，不輸出任何時間長度。

用法：
  python3 extract.py --db ~/.info-diet/history.db --days 30 \
      --report ~/.info-diet/report.txt --out ~/.info-diet/baseline.json

  # 確認過的本人帳號。寫成「平台:@帳號」比只寫「@帳號」準，
  # 因為同一個名字在別的平台上可能是別人。
  python3 extract.py --db ... --self "threads.com:@yourname,youtube.com:@YourChannel"
"""

import argparse
import collections
import datetime
import json
import os
import re
import sqlite3
import sys

# Chrome 時間戳：1601-01-01 起算的微秒。減掉這個差值就是 Unix epoch。
WEBKIT_TO_UNIX = 11_644_473_600

# transition 低 8 位 = 這次造訪怎麼發生的。3 = 自動載入的 iframe，
# 不是人點的，一律排除，否則廣告與追蹤碼會灌爆統計。
TRANSITION_AUTO_SUBFRAME = 3

# 「看自己」的路徑特徵：通知、私訊以外的自我監看入口
SELF_PATH_PAT = re.compile(
    r"^/(activity|notifications?|inbox|mentions|alerts|me|dashboard|analytics|insights)\b",
    re.I,
)
# 創作者／商業後台的網域特徵
SELF_HOST_PAT = re.compile(
    r"^(studio\.|creator\.|business\.|analytics\.|partner\.)", re.I
)
# 「還停在 feed 層」的路徑：首頁、推薦流、探索頁、搜尋結果頁
FEED_PATHS = {
    "/", "/home", "/explore", "/feed", "/foryou", "/for-you", "/browse",
    "/trending", "/popular", "/timeline", "/following", "/discover", "/reels",
    "/shorts", "/search", "/search_result", "/results", "/hot", "/new", "/all",
}
# 工具與工作台：這些不是「資訊攝取」，是在做事
WORK_HOST_PAT = re.compile(
    r"^(mail\.|docs\.|drive\.|calendar\.|sheets\.|slides\.|meet\.|console\.|"
    r"accounts?\.|login\.|auth\.|admin\.|manager\.|app\.|api\.|dashboard\.|"
    r"localhost|127\.0\.0\.1)",
    re.I,
)
WORK_DOMAINS = {
    # 開發與生產力
    "github.com", "gitlab.com", "stackoverflow.com", "localhost", "127.0.0.1",
    "notion.so", "figma.com", "trello.com", "asana.com", "linear.app",
    "vercel.com", "netlify.com", "huggingface.co", "canva.com",
    # 搜尋引擎：是查東西的工具，不是資訊來源
    "google.com", "bing.com", "duckduckgo.com", "baidu.com", "yandex.com",
    "perplexity.ai",
    # AI 工具
    "claude.ai", "chatgpt.com", "openai.com", "gemini.google.com",
    "aistudio.google.com", "poe.com", "grok.com",
}
# 通訊：一對一或群組對話，不是資訊攝取，也不是看自己
COMMS_DOMAINS = {
    "messenger.com", "line.me", "whatsapp.com", "telegram.org", "slack.com",
    "discord.com", "teams.microsoft.com", "zoom.us", "wechat.com",
}
# 消費型平台：這份清單「只是起手式」，不完整是正常的。
# 沒命中的會進 unclassified，交給 AI 跟使用者一起判斷——
# 在地新聞、小眾論壇、非英語平台不可能靠寫死的清單涵蓋。
CONSUME_DOMAINS = {
    "threads.com", "threads.net", "x.com", "twitter.com", "facebook.com",
    "instagram.com", "tiktok.com", "reddit.com", "youtube.com", "bilibili.com",
    "rednote.com", "xiaohongshu.com", "linkedin.com", "pinterest.com",
    "weibo.com", "news.ycombinator.com", "medium.com", "substack.com",
    "quora.com", "tumblr.com", "twitch.tv", "netflix.com", "9gag.com",
    "dcard.tw", "ptt.cc", "mobile01.com", "zhihu.com", "douyin.com",
}

# 看起來像 ID 的路徑片段：純數字、長雜湊、UUID、超長字串
ID_LIKE = re.compile(r"^([0-9]+|[0-9a-f]{8,}|[A-Za-z0-9_-]{16,})$")

# 預設就自動隱去的敏感類別。
#
# 這是安全網，不是保證。它一定會漏——關鍵字比對擋不掉沒見過的網站、
# 也擋不掉用代號的服務。真正的保護是「先問使用者要排除什麼」那一步，
# 這份清單只負責接住使用者自己沒想到要講的東西。
# 被擋下的只會以「敏感類別（已自動隱去）」的合計次數出現，網域名不會出現。
SENSITIVE_PAT = re.compile(
    r"(porn|xvideo|xnxx|pornhub|onlyfans|hentai|nsfw|escort|adult|"
    r"tinder|bumble|hinge|grindr|okcupid|match\.com|交友|約會|"
    r"clinic|hospital|medical|health|patient|symptom|therapy|psychiatr|"
    r"cancer|hiv|std|醫院|診所|健保|症狀|心理諮商|"
    r"jobs?|hire|recruit|career|resume|cv|linkedin\.com/jobs|104\.com|1111\.com|"
    r"yourator|cakeresume|求職|人力銀行|履歷|"
    r"casino|bet|poker|lottery|gambl|娛樂城|博弈|"
    r"lawyer|legal|attorney|divorce|律師|離婚|訴訟|"
    r"loan|debt|bankrupt|貸款|債務|破產)",
    re.I,
)


def is_sensitive(host, title, extra_terms, auto_redact):
    """
    判斷這一筆要不要直接隱去。隱去的東西連網域名都不會進報告。
    兩個來源各自獨立：內建清單（可用 --no-auto-redact 關掉）、
    使用者指名的關鍵字（永遠有效，關不掉）。
    """
    blob = f"{host} {title or ''}"
    if auto_redact and SENSITIVE_PAT.search(blob):
        return True
    low = blob.lower()
    return any(t in low for t in extra_terms)

# 這些不是帳號名，是網站自己的功能頁。不擋掉會把 /user/profile 認成一個叫
# profile 的人，然後跑去問使用者「這是你的帳號嗎」。
NOT_A_HANDLE = {
    "profile", "settings", "setting", "home", "me", "edit", "about", "login",
    "logout", "signup", "signin", "new", "search", "explore", "help", "account",
    "notifications", "messages", "inbox", "dashboard", "feed", "index",
}

BUCKETS = ("consume", "self", "comms", "work", "unclassified")
LABEL = {
    "consume": "外部攝取",
    "self": "看自己",
    "comms": "通訊對話",
    "work": "工具與工作台",
    "unclassified": "未分類（要人判斷）",
}


def split_url(url):
    """
    把網址拆成 (網域, 路徑片段清單)。查詢字串與錨點一律丟掉。
    只收 http/https：chrome-extension://、file://、about: 這些不是「上網」，
    收進來只會在未分類清單裡塞一堆亂碼般的擴充功能 ID。
    """
    m = re.match(r"^https?://([^/?#]+)([^?#]*)", url, re.I)
    if not m:
        return None, []
    host = m.group(1).lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    segs = [s for s in (m.group(2) or "/").split("/") if s]
    return host, segs


def path_shape(segs, keep=2):
    """
    把路徑收斂成「型態」，這是隱私的關鍵一步。
    /@someone/post/DMxK9    ->  /@someone/post
    /explore/6a6ac164000000   ->  /explore/:id
    只留前兩段，像 ID 的片段換成 :id。
    """
    if not segs:
        return "/"
    return "/" + "/".join(":id" if ID_LIKE.match(s) else s for s in segs[:keep])


def handle_of(segs):
    """抓出路徑裡的帳號名（/@name、/u/name、/user/name、/in/name）。"""
    if not segs:
        return None
    first = segs[0]
    if first.startswith("@") and len(first) > 1:
        name = first[1:].lower()
        return None if name in NOT_A_HANDLE else "@" + name
    if first in ("u", "user", "users", "in", "profile", "c") and len(segs) > 1:
        name = segs[1].lower()
        if not ID_LIKE.match(segs[1]) and name not in NOT_A_HANDLE:
            return "@" + name
    return None


# 標題前面的未讀數字，例如「(3) 某某文章」
TITLE_PREFIX = re.compile(r"^\s*\(\d+\)\s*")
# 各平台掛在標題尾巴的招牌，對判斷內容品質毫無幫助，拿掉比較好讀。
# 後面允許再跟一小段平台自己的行銷字（例如 Threads 的「, Say more」）。
TITLE_SUFFIX = re.compile(
    r"\s*[\|/•\-–—]\s*(X|Twitter|Threads|YouTube|Facebook|Instagram|Reddit|"
    r"LinkedIn|Medium|小紅書|RedNote|bilibili)\b[^|/•]*$",
    re.I,
)
# 純介面字串，不是內容。留著只會讓品質判斷變成在讀選單。
TITLE_UI_ONLY = re.compile(
    r"^(messages?|inbox|notifications?|home|首頁|訊息|通知|收件匣|"
    r"explore|探索|search|搜尋|settings|設定|dashboard|log ?in|sign ?in)$",
    re.I,
)


def clean_title(title):
    t = (title or "").strip()
    t = TITLE_PREFIX.sub("", t)
    for _ in range(2):                 # 有些標題會疊兩層招牌
        t = TITLE_SUFFIX.sub("", t).strip()
    t = t.strip(" -–—|•,")
    if TITLE_UI_ONLY.match(t):
        return ""
    return t if len(t) > 4 else ""


def base_domain(host):
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def classify(host, segs, shape, self_handles):
    """回傳這「一次造訪」屬於哪一類。按次造訪判斷，不是按網域。"""
    h = handle_of(segs)
    first = "/" + (segs[0] if segs else "")
    base = base_domain(host)

    # 1. 看自己：通知頁、後台、本人已確認的帳號頁
    if SELF_HOST_PAT.match(host):
        return "self"
    # 帳號名可以只寫 @xxx（所有平台通用），也可以寫 threads.com:@xxx（只認那個平台）。
    # 後者比較準：同一個名字在別的平台上可能是別人。
    if h and (h in self_handles or f"{host}:{h}" in self_handles):
        return "self"
    # 通知類路徑只在「消費型平台」上才算看自己，
    # 否則銀行的 /alerts、後台的 /dashboard 會被誤判
    if SELF_PATH_PAT.match(first) and (
        host in CONSUME_DOMAINS or base in CONSUME_DOMAINS
    ):
        return "self"

    # 2. 通訊
    if host in COMMS_DOMAINS or base in COMMS_DOMAINS:
        return "comms"

    # 3. 工具與工作台
    if host in WORK_DOMAINS or base in WORK_DOMAINS or WORK_HOST_PAT.match(host):
        return "work"

    # 4. 外部攝取
    if host in CONSUME_DOMAINS or base in CONSUME_DOMAINS:
        return "consume"

    return "unclassified"


def bar(n, mx, width=40):
    return "#" * int(n / mx * width) if mx else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="複製出來的 history.db")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default=None, help="輸出 baseline JSON 的路徑")
    ap.add_argument("--report", default=None,
                    help="把完整報告寫到這個檔，終端機只印狀態。"
                         "工作坊流程一定要用這個——讓使用者自己先看過、刪掉不想給的行，"
                         "AI 才讀得到。不加這個參數的話報告會直接印在終端機上，"
                         "而在 Claude Code 裡那等於 AI 當場就全看完了。")
    ap.add_argument("--self", dest="self_handles", default="",
                    help="已確認屬於本人的帳號，逗號分隔。"
                         "建議寫成「平台:@帳號」（例如 threads.com:@me,youtube.com:@MyChannel），"
                         "只認那個平台上的那個名字；"
                         "只寫「@帳號」的話所有平台通用，同名的別人會被誤認成本人。")
    ap.add_argument("--with-search", action="store_true",
                    help="額外輸出搜尋關鍵字（高敏感，預設關閉）")
    ap.add_argument("--with-titles", action="store_true",
                    help="額外輸出外部攝取類的網頁標題（品質模式）。"
                         "標題透露的東西遠多於網域，**必須另外取得使用者授權才能開**。"
                         "開了之後才判斷得出他吃進去的是不是好東西。")
    ap.add_argument("--exclude", default="",
                    help="使用者指名不想被分析的關鍵字或網域，逗號分隔。"
                         "命中的整筆直接丟掉，連網域名都不會進報告。")
    ap.add_argument("--no-auto-redact", action="store_true",
                    help="關掉內建敏感類別自動隱去。"
                         "只有在使用者明確說「我都可以給你看」時才用。")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    db = os.path.expanduser(args.db)
    if not os.path.exists(db):
        print(f"找不到檔案：{db}", file=sys.stderr)
        print("STATUS=nofile")
        return 1

    self_handles = set()
    for raw in args.self_handles.split(","):
        raw = raw.strip().lower()
        if not raw:
            continue
        if ":" in raw:                       # threads.com:@yourname
            host_part, name = raw.split(":", 1)
            self_handles.add(f"{host_part.strip()}:@{name.strip().lstrip('@')}")
        else:                                # @yourname（所有平台通用）
            self_handles.add("@" + raw.lstrip("@"))

    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = conn.execute(
            "select v.visit_time, v.transition, u.url, u.title "
            "from visits v join urls u on u.id = v.url"
        ).fetchall()
    except sqlite3.DatabaseError as e:
        print(f"讀不開這個檔：{e}", file=sys.stderr)
        print("STATUS=unreadable")
        return 1

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=args.days)

    dom_visits = collections.Counter()
    dom_days = collections.defaultdict(set)
    dom_shapes = collections.defaultdict(collections.Counter)
    dom_bucket_mix = collections.defaultdict(collections.Counter)
    bucket_visits = collections.Counter()
    handle_hits = collections.defaultdict(collections.Counter)
    hours = collections.Counter()
    days = collections.Counter()
    feed_n = detail_n = 0
    total = 0
    redacted = 0
    titles = collections.defaultdict(collections.Counter)   # host -> title -> n

    extra_terms = [t.strip().lower() for t in args.exclude.split(",") if t.strip()]

    for vtime, transition, url, title in rows:
        if (transition & 0xFF) == TRANSITION_AUTO_SUBFRAME:
            continue
        # 直接轉本機時間，不用手動處理時區
        when = datetime.datetime.fromtimestamp(vtime / 1_000_000 - WEBKIT_TO_UNIX)
        if when < cutoff or when > now + datetime.timedelta(days=1):
            continue
        host, segs = split_url(url)
        if not host:
            continue

        # 敏感或使用者指名排除的：只計數，其餘一律不留。
        # 這一段要放在所有統計之前，確保被隱去的網域名不會從任何管道流出去。
        if is_sensitive(host, title, extra_terms, not args.no_auto_redact):
            redacted += 1
            total += 1
            continue

        shape = path_shape(segs)
        bucket = classify(host, segs, shape, self_handles)
        h = handle_of(segs)
        if h:
            handle_hits[host][h] += 1

        total += 1
        bucket_visits[bucket] += 1
        dom_visits[host] += 1
        dom_days[host].add(when.date())
        dom_shapes[host][shape] += 1
        dom_bucket_mix[host][bucket] += 1
        hours[when.hour] += 1
        days[when.date().isoformat()] += 1

        # 只在「會滑的地方」算 feed vs 內容；工作台跟通訊不適用這個概念
        if bucket in ("consume", "self"):
            if shape in FEED_PATHS:
                feed_n += 1
            elif len(segs) >= 1:
                detail_n += 1

        # 標題只收「外部攝取」而且是點進單篇的——那才是他真的讀了什麼。
        # feed 層的標題多半是平台名稱，沒有判斷價值。
        if args.with_titles and bucket == "consume" and shape not in FEED_PATHS:
            t = clean_title(title)
            if t:
                titles[host][t] += 1

    if total == 0:
        print("這段期間沒有任何紀錄。可能是天數設太短，或挑錯了瀏覽器帳號。")
        print("STATUS=empty")
        return 0

    # ---------------- 給人看的輸出 ----------------
    # 全部先收進 OUT，最後再決定是印出來還是寫檔。
    # 這個區別是整個隱私承諾的關鍵：在 Claude Code 裡，print 出來的東西
    # 當下就進了 AI 的 context，「等一下再讓使用者刪」是假的。
    OUT = []

    def emit(line=""):
        OUT.append(line)

    emit("=" * 70)
    emit(f"資料範圍：最近 {args.days} 天　有效造訪 {total} 次　"
         f"涵蓋 {len(days)} 天、{len(dom_visits)} 個網域")
    emit("（已濾掉自動載入的內嵌內容；不含完整網址，但保留頁面型態與帳號名）")
    if redacted:
        emit(f"※ 另有 {redacted} 次（{redacted/total:.1%}）屬敏感類別或使用者指名排除，"
             f"已在產生報告時直接隱去，網域名不在這份報告裡。")
    emit("=" * 70)

    emit("\n--- 注意力去哪了（按每一次造訪計算）---")
    mx = max(bucket_visits.values())
    for b in BUCKETS:
        n = bucket_visits.get(b, 0)
        if not n:
            continue
        emit(f"  {LABEL[b]:<20}{n:>7}  {n/total:5.1%}  {bar(n, mx)}")

    known = feed_n + detail_n
    emit("\n--- 在社群與影音平台上：只滑，還是真的點進去讀 ---")
    if known >= 50:
        emit(f"  停在推薦流／首頁／搜尋結果  {feed_n:>7}  {feed_n/known:5.1%}")
        emit(f"  點進單篇內容                {detail_n:>7}  {detail_n/known:5.1%}")
    else:
        emit("  這類造訪太少，這項不解讀。")

    emit(f"\n--- 網域 Top {args.top} ---")
    emit(f"  {'次數':>7} {'活躍天':>6}  {'主要類型':<20} 網域")
    for d, n in dom_visits.most_common(args.top):
        mix = dom_bucket_mix[d]
        main_b, main_n = mix.most_common(1)[0]
        tag = LABEL[main_b]
        if len(mix) > 1 and main_n / n < 0.8:
            tag += "(混)"
        emit(f"  {n:>7} {len(dom_days[d]):>6}  {tag:<20} {d}")

    emit("\n--- 高頻網域在看什麼（路徑型態）---")
    for d, n in dom_visits.most_common(8):
        mix = " / ".join(f"{LABEL[b]}{c}" for b, c in dom_bucket_mix[d].most_common(3))
        emit(f"  [{d}]  共 {n} 次　→ {mix}")
        for shape, sn in dom_shapes[d].most_common(5):
            emit(f"      {sn:>6}  {shape}")

    emit("\n--- 疑似「本人帳號」候選（請跟使用者確認，別自己認定）---")
    found = False
    for host, hs in sorted(handle_hits.items(), key=lambda kv: -sum(kv[1].values())):
        top = hs.most_common(3)
        if not top or top[0][1] < 10:
            continue
        others = sum(v for _, v in top[1:])
        if top[0][1] >= max(10, others * 2):
            emit(f"  {host}: {top[0][0]}"
                 f"（{top[0][1]} 次；同平台其他帳號合計 {others} 次）")
            found = True
    if not found:
        emit("  沒有明顯候選。")
    emit("  確認之後重跑一次，加上 --self <帳號>，「看自己」那一欄才會準。")

    emit("\n--- 時段分佈（本機時間）---")
    mxh = max(hours.values())
    for h in range(24):
        n = hours.get(h, 0)
        emit(f"  {h:02d}:00  {n:>6}  {bar(n, mxh, 46)}")
    night = sum(hours.get(h, 0) for h in (0, 1, 2, 3, 4))
    emit(f"  凌晨 00-05 時合計：{night} 次（{night/total:.1%}）")

    unc = bucket_visits.get("unclassified", 0)
    if unc:
        emit(f"\n--- 未分類的網域（{unc} 次，{unc/total:.1%}）---")
        emit("  這些是內建清單沒有的網域。在地新聞、小眾論壇、非英語平台都會落在這裡，")
        emit("  這是預期行為，不是壞掉。請跟使用者一起判斷它們屬於哪一類：")
        shown = 0
        for d, n in dom_visits.most_common(200):
            if dom_bucket_mix[d].most_common(1)[0][0] != "unclassified":
                continue
            emit(f"      {n:>6}  {d}")
            shown += 1
            if shown >= 15:
                break

    if args.with_titles:
        emit("\n--- 他實際讀了什麼（品質模式，使用者已另外授權才會走到這裡）---")
        emit("  只收「外部攝取」而且點進單篇的頁面標題；停在推薦流那些不收。")
        emit("  判斷品質時看：標題是不是清一色情緒化或釣魚、主題是集中還是散、")
        emit("  有沒有需要花時間讀完的東西。判準見 references/quality-review.md。")
        shown_hosts = 0
        for host, tc in sorted(titles.items(), key=lambda kv: -sum(kv[1].values())):
            if sum(tc.values()) < 3:
                continue
            emit(f"\n  [{host}]  {sum(tc.values())} 次")
            for t, tn in tc.most_common(12):
                mark = f" x{tn}" if tn > 1 else ""
                emit(f"      {t[:90]}{mark}")
            shown_hosts += 1
            if shown_hosts >= 8:
                break
        if not shown_hosts:
            emit("  沒有足夠的單篇閱讀紀錄可以判斷——這件事本身就是一個發現。")

    if args.with_search:
        emit("\n--- 搜尋關鍵字（高敏感，使用者已明確同意才會走到這裡）---")
        try:
            for (term,) in conn.execute(
                "select term from keyword_search_terms order by rowid desc limit 60"
            ):
                emit(f"  {term}")
        except sqlite3.DatabaseError:
            emit("  這個瀏覽器沒有存搜尋關鍵字。")

    # 報告要嘛寫檔（使用者先看、先刪，AI 之後才讀），要嘛直接印。
    if args.report:
        rp = os.path.expanduser(args.report)
        os.makedirs(os.path.dirname(rp) or ".", exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print(f"報告已寫到：{rp}")
        print(f"共 {len(OUT)} 行。內容沒有印在這裡——這是刻意的。")
        print("下一步：問使用者有沒有不想被分析的東西，"
              "用 redact.py 依他說的關鍵字刪掉，刪完才讀這個檔。")
        print("REPORT_WRITTEN=1")
    else:
        print("\n".join(OUT))

    # ---------------- 給機器看的 baseline ----------------
    baseline = {
        "generated_at": now.isoformat(timespec="seconds"),
        "window_days": args.days,
        "total_visits": total,
        "days_covered": len(days),
        "buckets": {b: bucket_visits.get(b, 0) for b in BUCKETS},
        "feed_visits": feed_n,
        "detail_visits": detail_n,
        "late_night_visits": night,
        "top_domains": [
            {"domain": d, "visits": n, "active_days": len(dom_days[d]),
             "bucket": dom_bucket_mix[d].most_common(1)[0][0]}
            for d, n in dom_visits.most_common(args.top)
        ],
        "hours": {str(h): hours.get(h, 0) for h in range(24)},
    }
    if args.out:
        out = os.path.expanduser(args.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)
        print(f"\n基準值已存到：{out}")
        print("（下次重跑拿它比對，才看得出有沒有真的改變）")

    print("\nSTATUS=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
