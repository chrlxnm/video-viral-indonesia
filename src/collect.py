"""
Pengumpul video viral POLITIK Indonesia (bukan potongan TV) dari sumber gratis.

Sumber:
  1. YouTube (termasuk Shorts) lewat YouTube Data API resmi (gratis, kuota 10.000 unit/hari).
     Tanpa kata kunci: video paling banyak ditonton di Indonesia dari beberapa hari terakhir,
     per kategori. Patokan: MIN_VIEWS tayangan.
  2. Reddit (r/indonesia, lewat RSS tanpa kunci). Link X/Twitter di dalamnya dicek lewat
     endpoint embed publik X (patokan: MIN_LIKES_X like); link YouTube dicek lewat API YouTube.

Setelah itu video dari channel/akun TV dan media berita dibuang, lalu hasilnya disimpan
ke docs/videos.json untuk dashboard.

Kunci YouTube diambil dari variabel lingkungan YOUTUBE_API_KEY atau dari secrets.local.json:
  {"youtube_api_key": "..."}

Variabel lingkungan lain (opsional):
  MIN_VIEWS       tayangan minimum video YouTube (default 50000)
  MIN_LIKES_X     like minimum video X (default 10000)
  LOOKBACK_DAYS   1 = hanya video yang diunggah hari ini atau kemarin, WIB (default 1)
  MAX_DURATION    durasi maksimum video dalam detik (default 180 = batas YouTube Shorts)
  YT_CATEGORIES   ID kategori YouTube untuk pencarian umum, dipisah koma (default 22,25,24,2,15)
  YT_TYPE_QUERIES kata kunci jenis video, dipisah || (default cctv, detik-detik, terekam kamera,
                  rekaman warga, video amatir)
  SUBREDDITS      subreddit, dipisah koma (default indonesia)
  EXTRA_BLOCKED   nama channel/akun tambahan yang dibuang, dipisah koma
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "videos.json"
SECRETS_FILE = ROOT / "secrets.local.json"


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name) or default)


MIN_VIEWS = env_int("MIN_VIEWS", 50000)
MIN_LIKES_X = env_int("MIN_LIKES_X", 10000)
LOOKBACK_DAYS = env_int("LOOKBACK_DAYS", 1)  # 1 = hari ini + kemarin (WIB)
MAX_DURATION = env_int("MAX_DURATION", 180)  # detik; batas YouTube Shorts = 3 menit
WIB = dt.timezone(dt.timedelta(hours=7))


def window_start() -> dt.datetime:
    """Pukul 00:00 WIB, LOOKBACK_DAYS hari yang lalu."""
    today = dt.datetime.now(WIB).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - dt.timedelta(days=LOOKBACK_DAYS)


def parse_time(s: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def fits_window(posted_at: str | None, duration: int | None) -> bool:
    t = parse_time(posted_at)
    if t is None or t < window_start():
        return False
    return duration is not None and duration <= MAX_DURATION
# Khusus politik: kategori Berita & Politik (25) + kategori yang sering berisi konten
# politik dari kreator (People & Blogs 22, Hiburan 24). Tiap kategori = 100 unit kuota.
YT_CATEGORIES = [c.strip() for c in (os.getenv("YT_CATEGORIES") or "25,22,24").split(",") if c.strip()]
# Pencarian politik. Tiap kata kunci = 100 unit kuota per putaran.
YT_TYPE_QUERIES = [q.strip() for q in (
    os.getenv("YT_TYPE_QUERIES")
    or "politik||prabowo||jokowi||dpr||partai"
).split("||") if q.strip()]
SUBREDDITS = [s.strip() for s in (os.getenv("SUBREDDITS") or "indonesia").split(",") if s.strip()]
KEEP_HISTORY = 3000
UA = "Mozilla/5.0 (compatible; video-viral-indonesia/1.0; personal use)"

CATEGORY_NAMES = {
    "2": "Otomotif", "15": "Hewan", "17": "Olahraga", "19": "Perjalanan", "22": "People & Blogs",
    "23": "Komedi", "24": "Hiburan", "25": "Berita & Politik", "26": "Gaya hidup",
}

# ---------------------------------------------------------------- Saringan TV/media

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


BLOCKED = {norm(a) for a in [
    "kompastv", "kompas tv", "kompascom", "metro tv", "metrotv", "metrotvnews", "tvonenews", "tvone",
    "cnn indonesia", "cnnindonesia", "cnbc indonesia", "detikcom", "detiknews", "20detik", "liputan6",
    "liputan6dotcom", "tribunnews", "tribun timur", "inews", "inews id", "official inews", "inewsdotid",
    "kumparan", "idn times", "okezone", "sindonews", "beritasatu", "beritasatu tv", "rcti", "sctv",
    "indosiar", "antv", "trans tv", "trans7", "transtv_corp", "official_trans7", "tempo", "tempodotco",
    "narasi", "narasi newsroom", "narasitv", "suaracom", "republika", "jawapos", "antara", "antaranews",
    "vivacoid", "tvri", "tvri nasional", "gtv", "mnctv", "kompasiana", "jpnn", "merdekacom", "medcom",
    "pikiran rakyat", "solopos", "net", "netmediatama", "moji", "rtv", "ntv", "jaktv", "bandung tv",
]}
BLOCKED |= {norm(a) for a in (os.getenv("EXTRA_BLOCKED") or "").split(",") if a.strip()}

MEDIA_NAME_RE = re.compile(
    r"(?:^|[^a-z])tv|tv(?:$|[^a-z])|news|berita|kompas|detik|tribun|liputan|official|inilah"
    r"|\.com|\bcom\b|com$|\.co\.id|\.id$",
    re.IGNORECASE,
)
TV_TEXT_RE = re.compile(
    r"kompas ?tv|metro ?tv|tv ?one|cnn ?indonesia|liputan ?6|inews|#beritaterkini|siaran langsung"
    r"|live report|saksikan (?:selengkapnya|di)|tonton (?:selengkapnya|di)|program .+ tv"
    r"|subscribe (?:channel )?(?:kompas|cnn|tvone|metro|inews)",
    re.IGNORECASE,
)

# Kata-kata umum bahasa Indonesia untuk menebak bahasa judul/deskripsi.
INDO_WORDS = set("""
yang di dan ini itu dari tidak ada untuk dengan saat ketika sampai jadi bikin aksi detik detik
warga pengendara jalan motor mobil viral terekam kecelakaan banjir pria wanita emak bocah anak
kejadian heboh ngeri lagi sudah akan bisa langsung tiba tiba begini kayak gak nggak banget aja
""".split())


# Kata/nama yang menandakan video politik (dicek di judul + awal deskripsi).
POLITICS_RE = re.compile(
    r"\b(?:prabowo|jokowi|gibran|anies|ganjar|megawati|puan|kaesang|bahlil|luhut|sby|ahy|mahfud"
    r"|presiden|wapres|wakil presiden|menteri|mentri|kabinet|istana|dpr|dprd|mpr|parpol|partai"
    r"|pdip|pdi-?p|gerindra|golkar|nasdem|pkb|pks|psi|demokrat|pemilu|pilkada|pilpres|kampanye"
    r"|caleg|capres|cawapres|gubernur|bupati|walikota|wali kota|kapolri|wakapolri|panglima|tni|polri"
    r"|kpk|korupsi|koruptor|mk|mahkamah|dpd|ketum|ketua umum|politik|politisi|politikus|oposisi"
    r"|demo|demonstrasi|unjuk rasa|ruu|undang-undang|perppu|roy suryo|dr tifa|rismon|listyo|ijazah jokowi|makar"
    r"|penyadapan|kudeta|rezim|pemerintah|pejabat|legislatif|eksekutif|parlemen)\b",
    re.IGNORECASE,
)


def topic_of(title: str, text: str) -> str:
    return "politik" if POLITICS_RE.search(f"{title or ''}\n{(text or '')[:500]}") else "umum"


HINDI_WORDS = set("hai ki ka ke aur nahi kya me se bhai ko wala wali kaise".split())


def tv_or_media_reason(handle: str, name: str, text: str) -> str | None:
    if norm(handle) in BLOCKED or norm(name) in BLOCKED:
        return "Channel/akun TV atau media berita (daftar blokir)."
    if MEDIA_NAME_RE.search(handle or "") or MEDIA_NAME_RE.search(name or ""):
        return "Nama channel/akun mirip TV atau media berita."
    if TV_TEXT_RE.search(text or ""):
        return "Teks mirip potongan tayangan TV."
    return None


def looks_indonesian(text: str, lang: str | None) -> bool:
    # Label bahasa channel sering asal diisi, jadi tetap wajib ada kata Indonesia di teksnya.
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    if len(words & HINDI_WORDS) >= 2:  # Hindi/Urdu latin sering lolos karena label bahasa salah
        return False
    hits = len(words & INDO_WORDS)
    if lang and lang.lower().startswith(("id", "in")):
        return hits >= 1
    return hits >= 2


def log(msg: str) -> None:
    print(f"[collect] {msg}", flush=True)


# ---------------------------------------------------------------- YouTube

class QuotaExceeded(Exception):
    pass


def load_youtube_key() -> str | None:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key and SECRETS_FILE.exists():
        try:
            key = json.loads(SECRETS_FILE.read_text(encoding="utf-8-sig")).get("youtube_api_key")
        except (json.JSONDecodeError, OSError):
            key = None
    return key.strip() if key else None


def yt_get(key: str, path: str, params: dict) -> dict:
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{path}",
                     params={**params, "key": key}, timeout=30)
    if r.status_code == 403 and "quota" in r.text.lower():
        raise QuotaExceeded()
    if r.status_code in (400, 403):
        raise SystemExit(f"Kunci YouTube ditolak (HTTP {r.status_code}): {r.text[:300]}")
    r.raise_for_status()
    return r.json()


def iso_duration(s: str) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def youtube_details(key: str, sources: dict[str, str]) -> list[dict]:
    """sources: {video_id: keterangan sumber}. Mengembalikan video yang lolos patokan tayangan."""
    out = []
    ids = list(sources)
    for i in range(0, len(ids), 50):
        data = yt_get(key, "videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
        for v in data.get("items", []):
            sn, st, cd = v["snippet"], v.get("statistics", {}), v.get("contentDetails", {})
            views = int(st.get("viewCount", 0))
            if views < MIN_VIEWS or sn.get("liveBroadcastContent", "none") != "none":
                continue
            desc = sn.get("description", "")
            if not looks_indonesian(f"{sn['title']} {desc[:400]}",
                                    sn.get("defaultAudioLanguage") or sn.get("defaultLanguage")):
                continue
            thumbs = sn.get("thumbnails", {})
            thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
            dur = iso_duration(cd.get("duration", ""))
            if not fits_window(sn.get("publishedAt"), dur):
                continue
            out.append({
                "id": f"yt:{v['id']}",
                "platform": "youtube",
                "url": (f"https://www.youtube.com/shorts/{v['id']}" if dur and dur <= 60
                        else f"https://www.youtube.com/watch?v={v['id']}"),
                "youtube_id": v["id"],
                "title": sn["title"],
                "text": desc[:3000],
                "author": sn.get("channelTitle", ""),
                "author_url": f"https://www.youtube.com/channel/{sn.get('channelId', '')}",
                "views": views,
                "likes": int(st["likeCount"]) if "likeCount" in st else None,
                "duration": dur,
                "thumbnail": thumb,
                "posted_at": sn.get("publishedAt"),
                "source": sources[v["id"]],
                "video_url": None,
                "excluded_reason": tv_or_media_reason(sn.get("channelTitle", ""), sn.get("channelTitle", ""),
                                                      f"{sn['title']}\n{desc[:600]}"),
            })
    return out


def collect_youtube(key: str) -> list[dict]:
    since = window_start().astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sources: dict[str, str] = {}
    # videoDuration=short = di bawah 4 menit; batas 60 detik dicek lagi saat mengambil detail.
    base = {"part": "id", "type": "video", "regionCode": "ID", "relevanceLanguage": "id",
            "publishedAfter": since, "order": "viewCount", "maxResults": 50, "safeSearch": "none",
            "videoDuration": "short"}
    # Pencarian jenis lebih dulu, supaya video yang cocok diberi label jenisnya.
    searches = [({"q": q}, f"YouTube · cari: {q.strip(chr(34))}") for q in YT_TYPE_QUERIES]
    searches += [({"videoCategoryId": c}, f"YouTube · {CATEGORY_NAMES.get(c, c)}") for c in YT_CATEGORIES]
    for extra, label in searches:
        try:
            data = yt_get(key, "search", {**base, **extra})
        except QuotaExceeded:
            log("Kuota harian YouTube habis. Lanjut dengan hasil yang sudah ada.")
            break
        except requests.RequestException as e:
            log(f"Pencarian YouTube ({label}) gagal: {e}")
            continue
        for it in data.get("items", []):
            vid = it.get("id", {}).get("videoId")
            if vid:
                sources.setdefault(vid, label)
    log(f"YouTube: {len(sources)} video kandidat dari {len(YT_TYPE_QUERIES)} pencarian jenis "
        f"dan {len(YT_CATEGORIES)} kategori.")
    try:
        items = youtube_details(key, sources)
    except QuotaExceeded:
        log("Kuota harian YouTube habis saat mengambil detail video.")
        items = []
    log(f"YouTube: {len(items)} video lolos (≥{MIN_VIEWS:,} tayangan, ≤{MAX_DURATION} detik, "
        f"hari ini/kemarin, berbahasa Indonesia).")
    return items


# ---------------------------------------------------------------- X (embed publik)

X_STATUS_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter|fixupx|fxtwitter|vxtwitter|fixvx)\.com/"
    r"(?:[A-Za-z0-9_]+|i/web)/status(?:es)?/(\d+)", re.IGNORECASE)
YT_LINK_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:[^\"'\s<]*&)?v=|shorts/)|youtu\.be/)([\w-]{11})")


def x_item(tweet_id: str, source: str) -> dict | None:
    try:
        r = requests.get("https://cdn.syndication.twimg.com/tweet-result",
                         params={"id": tweet_id, "lang": "en", "token": "a"},
                         headers={"User-Agent": UA}, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.text.strip():
        return None
    d = r.json()
    video = next((m for m in d.get("mediaDetails") or [] if m.get("type") == "video"), None)
    if not video:
        return None
    likes = int(d.get("favorite_count") or 0)
    if likes < MIN_LIKES_X:
        return None
    info = video.get("video_info", {})
    mp4s = [v for v in info.get("variants", []) if v.get("content_type") == "video/mp4"]
    if not mp4s:
        return None
    user = d.get("user", {})
    sn, text = user.get("screen_name", ""), d.get("text", "")
    dur = info.get("duration_millis")
    if not fits_window(d.get("created_at"), round(dur / 1000) if dur else None):
        return None
    return {
        "id": f"x:{tweet_id}",
        "platform": "x",
        "url": f"https://x.com/{sn}/status/{tweet_id}",
        "title": text.split("\n")[0][:140],
        "text": text,
        "author": f"@{sn}",
        "author_url": f"https://x.com/{sn}",
        "views": None,
        "likes": likes,
        "duration": round(dur / 1000) if dur else None,
        "thumbnail": video.get("media_url_https"),
        "posted_at": d.get("created_at"),
        "source": source,
        "video_url": max(mp4s, key=lambda v: v.get("bitrate") or 0)["url"],
        "excluded_reason": tv_or_media_reason(sn, user.get("name", ""), text),
    }


# ---------------------------------------------------------------- Reddit

ATOM = {"a": "http://www.w3.org/2005/Atom"}


def collect_reddit(yt_key: str | None) -> list[dict]:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    x_ids: dict[str, str] = {}
    yt_ids: dict[str, str] = {}
    for sub in SUBREDDITS:
        r = None
        for attempt in range(3):
            try:
                r = s.get(f"https://www.reddit.com/r/{sub}/top/.rss", params={"t": "week", "limit": 100}, timeout=30)
            except requests.RequestException as e:
                log(f"Reddit r/{sub} gagal: {e}")
                r = None
                break
            if r.status_code != 429:
                break
            time.sleep(20 * (attempt + 1))
        if r is None or r.status_code != 200:
            log(f"Reddit r/{sub} tidak bisa diambil" + (f" (HTTP {r.status_code})" if r is not None else "") + ".")
            continue
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            continue
        for e in root.findall("a:entry", ATOM):
            content = html.unescape(e.findtext("a:content", "", ATOM))
            for tid in X_STATUS_RE.findall(content):
                x_ids.setdefault(tid, f"Reddit r/{sub}")
            for vid in YT_LINK_RE.findall(content):
                yt_ids.setdefault(vid, f"Reddit r/{sub}")
        time.sleep(3)

    items = []
    for tid, src in x_ids.items():
        it = x_item(tid, src)
        if it:
            items.append(it)
        time.sleep(1)
    if yt_ids and yt_key:
        try:
            items += youtube_details(yt_key, yt_ids)
        except QuotaExceeded:
            pass
    log(f"Reddit: {len(x_ids)} link X dan {len(yt_ids)} link YouTube, {len(items)} lolos patokan.")
    return items


# ---------------------------------------------------------------- Riwayat

def load_history() -> list[dict]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8")).get("items", [])
        except (json.JSONDecodeError, OSError):
            log("videos.json rusak, mulai dari kosong.")
    return []


def save_history(items: list[dict]) -> None:
    DATA_FILE.parent.mkdir(exist_ok=True)
    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "min_views": MIN_VIEWS,
        "min_likes_x": MIN_LIKES_X,
        "items": items[:KEEP_HISTORY],
    }
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    yt_key = load_youtube_key()
    candidates: list[dict] = []
    if yt_key:
        candidates += collect_youtube(yt_key)
    else:
        log("Kunci YouTube belum diisi: sumber YouTube dilewati. Lihat README langkah 2.")
    candidates += collect_reddit(yt_key)

    by_id = {it["id"]: it for it in load_history()}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    new = 0
    for c in candidates:
        c["topic"] = topic_of(c.get("title", ""), c.get("text", ""))
        if c["topic"] != "politik":  # khusus politik: selain itu tidak disimpan
            continue
        status = "excluded" if c["excluded_reason"] else "ok"
        old = by_id.get(c["id"])
        if old:
            by_id[c["id"]] = {**old, **c, "status": status, "checked_at": now}
        else:
            by_id[c["id"]] = {**c, "status": status, "found_at": now, "checked_at": now}
            new += status == "ok"

    # Hanya simpan video yang masih masuk jendela waktu (hari ini/kemarin) dan ≤ MAX_DURATION.
    kept = [it for it in by_id.values() if fits_window(it.get("posted_at"), it.get("duration"))
            and (it.get("platform") != "youtube" or looks_indonesian(f"{it.get('title')} {it.get('text')}", None))]
    for it in kept:  # riwayat lama juga diberi topik
        it["topic"] = topic_of(it.get("title", ""), it.get("text", ""))
    kept = [it for it in kept if it["topic"] == "politik"]
    items = sorted(kept, key=lambda x: x.get("found_at", ""), reverse=True)
    save_history(items)
    log(f"Selesai: {new} video baru. Total riwayat {len(items)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
