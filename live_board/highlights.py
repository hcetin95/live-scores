"""Find official YouTube highlights for finished games and write site/highlights.json.

Runs every 15 minutes in GitHub Actions. With a YOUTUBE_API_KEY secret it reads each
official channel's last ~200 uploads (YouTube Data API, about 3,000 of the 10,000 free
daily quota units). Without a key it falls back to the public RSS feed (15 newest videos).
"updated" only changes when the results change, so quiet runs don't commit.

Output: {"updated": iso, "items": {espn_event_id: {url, title, channel, published, kick}},
         "matchday": {"CL": {url, title, channel, published, round}}}  (newest all-goals video)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
UA = {"User-Agent": "hcetin95-live-board/1.0 (+https://github.com)"}

# League slug -> official channels (YouTube handles) that post US highlights.
CHANNELS = {
    "uefa.champions": ["CBSSportsGolazo"],
    "ita.1": ["CBSSportsGolazo"],
    "eng.1": ["NBCSports"],
    "esp.1": ["ESPNFC", "LaLiga"],
    "ger.1": ["bundesliga"],
    "fra.1": ["beINSPORTSUSA", "Ligue1"],
    "tur.1": ["beINSPORTSTurkiye", "Fenerbahce"],
}
# Channels for the "all goals of the matchday" compilation, in order of preference (US-friendly first).
MATCHDAY_CHANNELS = {"CL": ["CBSSportsGolazo", "UEFA", "ChampionsLeague"]}
MATCHDAY_KEEP_DAYS = 21
KEEP_DAYS = 10
LOOKBACK_DAYS = 3
HL_WORDS = ("highlight", "ozet", "özet", "goals", "resumen", "all goals")
FOLD_EXTRA = str.maketrans({"ø": "o", "ß": "ss", "ı": "i", "æ": "ae", "ð": "d", "ł": "l"})
STOP = {"fc", "cf", "sc", "ac", "as", "ss", "sk", "afc", "club", "de", "the", "real", "city", "united", "sporting", "athletic"}


def fold(s: str) -> str:
    s = (s or "").lower().translate(FOLD_EXTRA)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def aliases(team: dict) -> set[str]:
    """Ways a title may name this team."""
    out = set()
    for k in ("displayName", "shortDisplayName", "name", "location", "abbreviation"):
        v = fold(team.get(k, ""))
        if v:
            out.add(v)
    # distinctive single words ("Bodo/Glimt" -> "glimt", "Nottingham Forest" -> "forest")
    for v in list(out):
        for w in v.split():
            if len(w) >= 5 and w not in STOP:
                out.add(w)
    return {a for a in out if len(a) >= 3}


def mentions(title: str, names: set[str]) -> bool:
    t = f" {fold(title)} "
    return any(f" {a} " in t for a in names)


def is_highlight(title: str) -> bool:
    t = fold(title)
    return any(fold(w) in t for w in HL_WORDS) and "preview" not in t and "press conference" not in t


def finished_games(today: dt.date) -> list[dict]:
    games, seen = [], set()
    for slug in CHANNELS:
        for back in range(LOOKBACK_DAYS + 1):
            day = today - dt.timedelta(days=back)
            try:
                data = json.loads(get(f"{ESPN}/{slug}/scoreboard?dates={day:%Y%m%d}"))
            except Exception as e:  # noqa: BLE001
                print(f"ESPN {slug} {day}: {e}", file=sys.stderr)
                continue
            for ev in data.get("events") or []:
                comp = (ev.get("competitions") or [{}])[0]
                if ((comp.get("status") or {}).get("type") or {}).get("state") != "post":
                    continue
                eid = str(ev.get("id"))
                if eid in seen:
                    continue
                seen.add(eid)
                cs = comp.get("competitors") or []
                home = next((c for c in cs if c.get("homeAway") == "home"), {}).get("team") or {}
                away = next((c for c in cs if c.get("homeAway") == "away"), {}).get("team") or {}
                games.append({"id": eid, "slug": slug, "kick": ev.get("date"),
                              "home": aliases(home), "away": aliases(away),
                              "label": f"{home.get('displayName')} v {away.get('displayName')}"})
    return games


def channel_id(handle: str, cache: dict) -> str | None:
    if handle in cache:
        return cache[handle]
    try:
        html = get(f"https://www.youtube.com/@{handle}").decode("utf-8", "replace")
        m = re.search(r'"externalId":"(UC[\w-]{22})"', html) or re.search(r'channel/(UC[\w-]{22})', html)
        cache[handle] = m.group(1) if m else None
    except Exception as e:  # noqa: BLE001
        print(f"channel @{handle}: {e}", file=sys.stderr)
        cache[handle] = None
    return cache[handle]


def feed(cid: str) -> list[dict]:
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    root = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
    author = root.findtext("a:title", default="", namespaces=ns)
    out = []
    for e in root.findall("a:entry", ns):
        vid = e.findtext("yt:videoId", default="", namespaces=ns)
        out.append({"title": e.findtext("a:title", default="", namespaces=ns),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "published": e.findtext("a:published", default="", namespaces=ns), "channel": author})
    return out


def match(game: dict, videos: list[dict]) -> dict | None:
    kick = dt.datetime.fromisoformat(game["kick"].replace("Z", "+00:00"))
    best = None
    for v in videos:
        if not (is_highlight(v["title"]) and mentions(v["title"], game["home"]) and mentions(v["title"], game["away"])):
            continue
        try:
            pub = dt.datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if pub < kick:
            continue
        score = ("extended" in fold(v["title"])) * 2 + ("highlight" in fold(v["title"]))
        if best is None or score > best[0]:
            best = (score, v)
    return best[1] if best else None


def uploads(cid: str, key: str, since: str, pages: int = 4) -> list[dict]:
    """Recent uploads via the YouTube Data API (playlistItems costs 1 quota unit per 50 videos)."""
    out, token = [], ""
    for _ in range(pages):
        q = {"part": "snippet", "playlistId": "UU" + cid[2:], "maxResults": 50, "key": key}
        if token:
            q["pageToken"] = token
        data = json.loads(get("https://www.googleapis.com/youtube/v3/playlistItems?" + urllib.parse.urlencode(q)))
        for i in data.get("items") or []:
            sn = i.get("snippet") or {}
            vid = (sn.get("resourceId") or {}).get("videoId")
            if vid:
                out.append({"title": sn.get("title", ""), "url": f"https://www.youtube.com/watch?v={vid}",
                            "published": sn.get("publishedAt", ""), "channel": sn.get("channelTitle", "")})
        token = data.get("nextPageToken")
        if not token or (out and out[-1]["published"] < since):
            break
    return out


ROUND = re.compile(r"\b(?:matchday|md)\s*(\d{1,2})\b")


def is_matchday_goals(title: str) -> bool:
    t = f" {fold(title)} "
    goals = any(w in t for w in (" all goals ", " all the goals ", " every goal ", " todos los goles "))
    ucl = " ucl " in t or " champions league " in t
    other = any(w in t for w in (" europa ", " conference ", " uwcl ", " women ", " youth "))
    return goals and ucl and not other and bool(ROUND.search(t))


def plays_in_us(vid_url: str, key: str) -> bool:
    """True unless the YouTube API says the video is blocked in the US (needs a key; assume yes without)."""
    if not key:
        return True
    vid = urllib.parse.parse_qs(urllib.parse.urlparse(vid_url).query).get("v", [""])[0]
    q = urllib.parse.urlencode({"part": "contentDetails,status", "id": vid, "key": key})
    try:
        items = json.loads(get(f"https://www.googleapis.com/youtube/v3/videos?{q}")).get("items") or []
    except Exception as e:  # noqa: BLE001
        print(f"region check {vid}: {e}", file=sys.stderr)
        return True
    if not items:
        return False
    rr = (items[0].get("contentDetails") or {}).get("regionRestriction") or {}
    if (items[0].get("status") or {}).get("privacyStatus", "public") != "public":
        return False
    if "allowed" in rr:
        return "US" in rr["allowed"]
    return "US" not in rr.get("blocked", [])


def pick_matchday(videos: list[dict], key: str) -> dict | None:
    """Newest all-goals compilation that plays in the US."""
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MATCHDAY_KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    cands = sorted((v for v in videos if is_matchday_goals(v["title"]) and v["published"][:19] >= cutoff),
                   key=lambda v: v["published"], reverse=True)
    for v in cands[:3]:
        if plays_in_us(v["url"], key):
            return {**v, "round": int(ROUND.search(fold(v["title"])).group(1))}
    return None


def run(out_path: pathlib.Path, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    try:
        prev = json.loads(out_path.read_text())
    except (FileNotFoundError, ValueError):
        prev = {}
    items = prev.get("items", {})
    cids_cache = prev.get("channels", {})
    games = [g for g in finished_games(today) if g["id"] not in items]
    feeds: dict[str, list[dict]] = {}
    key = os.environ.get("YOUTUBE_API_KEY", "")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=LOOKBACK_DAYS + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = 0
    def videos(c: str) -> list[dict]:
        if c not in feeds:
            feeds[c] = []
            if key:
                try:
                    feeds[c] = uploads(c, key, since)
                except Exception as e:  # noqa: BLE001
                    print(f"YouTube API {c}: {e}", file=sys.stderr)
            if not feeds[c]:
                try:
                    feeds[c] = feed(c)
                except Exception as e:  # noqa: BLE001
                    print(f"feed {c}: {e}", file=sys.stderr)
        return feeds[c]

    for g in games:
        cids = [c for c in (channel_id(h, cids_cache) for h in CHANNELS[g["slug"]]) if c]
        vids = [v for c in cids for v in videos(c)]
        hit = match(g, vids)
        if hit:
            items[g["id"]] = {**hit, "kick": g["kick"]}
            found += 1
            print(f"found: {g['label']} -> {hit['title']}")
    matchday = dict(prev.get("matchday") or {})
    for comp, handles in MATCHDAY_CHANNELS.items():
        got = None
        for h in handles:  # first channel with a compilation wins (CBS Golazo is US-licensed)
            c = channel_id(h, cids_cache)
            if c:
                vs = videos(c)
                for v in vs:  # log near-misses so title-format changes are easy to spot
                    t = fold(v["title"])
                    if "goal" in t and ("ucl" in t or "champions league" in t) and "highlights" not in t:
                        print(f"  matchday candidate @{h}: {v['title']} ({'ok' if is_matchday_goals(v['title']) else 'no'})")
                got = pick_matchday(vs, key)
                if got:
                    break
        old = matchday.get(comp)  # keep the previous matchday's video until a newer one appears
        if got and (not old or got["published"] > old.get("published", "")):
            matchday[comp] = got
            print(f"matchday {comp}: {got['title']}")
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=KEEP_DAYS)).isoformat()
    items = {k: v for k, v in items.items() if (v.get("kick") or v.get("published", "")) >= cutoff[:19]}
    pending = [g["label"] for g in games if g["id"] not in items]
    same = (items == prev.get("items") and pending == prev.get("pending") and cids_cache == prev.get("channels")
            and matchday == (prev.get("matchday") or {}))
    stamp = prev.get("updated") if same and prev.get("updated") else dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {"updated": stamp, "items": items, "matchday": matchday, "channels": cids_cache, "pending": pending}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(games)} finished games without highlights checked, {found} found, {len(items)} total")
    return out


if __name__ == "__main__":
    run(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "live_board/site/highlights.json"))
