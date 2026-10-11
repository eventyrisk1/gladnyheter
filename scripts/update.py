"""Gladnyheter: henter norske RSS-feeder, velger de 10 beste sakene + 1 sportssak
og skriver resultatet til data.json. Kjøres hver time av GitHub Actions (gratis).

Utvalget gjøres med faste regler (filter + poeng). Hvis du senere legger inn en
Claude API-nøkkel som secret ANTHROPIC_API_KEY, brukes Claude i stedet automatisk.
"""
import json, os, re, sys, html, urllib.request, urllib.error, datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")

# (kilde, url, kildepoeng)
FEEDS = [
    ("forskning.no", "https://www.forskning.no/rss", 3),
    ("Gemini", "https://gemini.no/feed/", 3),
    ("NRK", "https://www.nrk.no/viten/toppsaker.rss", 3),
    ("NRK", "https://www.nrk.no/kultur/toppsaker.rss", 2),
    ("Teknisk Ukeblad", "https://www.tu.no/rss", 2),
    ("Aftenposten", "https://www.aftenposten.no/rss/kultur", 2),
    ("E24", "https://e24.no/rss2/", 1),
    ("NRK", "https://www.nrk.no/toppsaker.rss", 1),
    ("NRK", "https://www.nrk.no/norge/toppsaker.rss", 1),
    ("Aftenposten", "https://www.aftenposten.no/rss", 0),
    ("VG", "https://www.vg.no/rss/feed", 0),
]
SPORT_FEEDS = [
    ("NRK", "https://www.nrk.no/sport/toppsaker.rss", 1),
    ("VG", "https://www.vg.no/rss/feed/?categories=1072&limit=40", 0),
    ("Aftenposten", "https://www.aftenposten.no/rss/sport", 0),
]

# Alt dette kastes: negativt, skremmende, kriminalitet, krig, kjendis/influenser, quiz osv.
BLOCK = re.compile(
    r"\b(krig|drept|drap|dødsfall|omkom|døde|død |dør |skutt|skyting|knivstikk|terror|angrep|bombe|missil|rakett|"
    r"voldtekt|overgrep|vold\b|voldelig|siktet|tiltalt|dømt|fengsel|fengslet|pågrepet|arrestert|politiet|politimann|ulykke|kollisjon|"
    r"brann|eksplo|katastrofe|jordskjelv|flom|skred|\bras\b|storm|uvær|gaza|ukraina|russland|putin|israel|hamas|"
    r"iran|nato|atomvåpen|atomkraftulykke|selvmord|kreft(?!fri)|opereres|operasjon|sykehus|svulst|diagnose|\bsyke?\b|pasient|sykdom|smitte|pandemi|trump|influenser|kjendis|instagram|tiktok|reality|"
    r"paradise hotel|farmen|skal vi danse|quiz|kryssord|se bildene|se video|høydepunkt|på \d+ minutter|"
    r"tegneserie|dagens lunch|dagens dunce|konkurs|permitter|nedlegg|kutt|streik(?! avverget)|savnet|"
    r"alarm|frykt|advar|trussel|sjokk|skandale|rase|raste|slakt|knus|bråk|krangel|rettssak|søksmål|saksøk|"
    r"etterforsk|anklag|mistenkt|sikkerhetsbrudd|hack|svindel|bedrag|rasis|hets\b|hat\b|hatet|mobb|demonstr|protest)",
    re.I,
)
# Klikkagn-mønstre i titler
CLICKBAIT = re.compile(
    r"(\(\d{1,3}\)|^–|^-|: –|: -|dette er|her er|slik |sjekk|du vil|du må|ikke tro|avslør|hemmelig|"
    r"utrolig|vanvittig|helt rå|alle snakker|reagerer|hylles|får kritikk|tar et oppgjør|går til angrep|"
    r"ber om unnskyldning|bryter tausheten|åpner opp|forteller om|mener at|kommentar|debatt|leder:)",
    re.I,
)
# Opinion/kommentar i URL
SKIP_URL = re.compile(r"/(video|kommentar|debatt|meninger|leder|kronikk|ytring|quiz|tegneserier|hjernetrim)/", re.I)

TOPICS = [
    ("Historie", 3, r"arkeolog|viking|historie|middelalder|skatten\b|mynt|ruin|fortid|museum"),
    ("Vitenskap", 3, r"forsk|studie|oppdag|funn|nobel|univers|planet|romfart|astronom|fysikk|kjemi|matemat"),
    ("Medisin", 2, r"behandling|medisin|vaksine|terapi|helse|trening|kosthold|søvn"),
    ("Teknologi", 2, r"teknolog|\bki\b|kunstig intelligens|robot|batteri|elbil|lading|sensor|brikke|\bdata|\bapp\b|software|digital"),
    ("Natur", 3, r"natur|dyr|fugl|fisk|hval|fjellrev|\brev(en)?\b|ulv|elg|reinsdyr|villrein|bjørn|insekt|skog|\bhav(et)?\b|\barter?\b|miljø|klima|co2|karbon|fornybar|solenergi|solcelle|vindkraft|vern"),
    ("Kultur", 2, r"film|serie|bok|roman|forfatter|musikk|album|konsert|kunst|teater|ballett|tegneserie|kultur|maleri|kunstner|\bpris(en|vinner)?\b"),
    ("Næringsliv", 2, r"gründer|oppstart|bedrift|selskap|eksport|netthandel|handel|butikk|innovasjon|marked"),
    ("Økonomi", 2, r"rente|prisvekst|inflasjon|norges bank|strømpris|norgespris|statsbudsjett|skatt|lønn|bolig"),
    ("Hverdag", 2, r"avverget|enige|åpner|ny vei|tog|fly|reise|ferie|regler|\blov\b|forbud"),
]
POSITIVE = re.compile(r"rekord|gjennombrudd|løst|lykkes|vant|vinner|gull|seier|redd|ny art|første|endelig|bedre|suksess", re.I)

UA = {"User-Agent": "Mozilla/5.0 (Gladnyheter.no RSS-leser)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def clean(s, n=None):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n:
        s = s[:n].rsplit(" ", 1)[0] + " …"
    return s


def strip_utm(u):
    return re.sub(r"[?&]utm_[^&#]+", "", u or "").rstrip("?&")


def tag(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
    v = m.group(1) if m else ""
    return re.sub(r"^\s*<!\[CDATA\[(.*?)\]\]>\s*$", r"\1", v, flags=re.S)


def parse(source, url, weight, limit=25):
    items = []
    try:
        raw = fetch(url).decode("utf-8", "replace")
    except Exception as e:
        print(f"Feil: {url}: {e}", file=sys.stderr)
        return items
    now = datetime.datetime.now(datetime.timezone.utc)
    for pos, block in enumerate(re.findall(r"<item[\s>].*?</item>", raw, re.S)[:limit]):
        t = clean(tag(block, "title"))
        link = strip_utm(clean(tag(block, "link")))
        d = clean(tag(block, "description"), 220)
        if not t or not link:
            continue
        age_h = None
        try:
            age_h = (now - parsedate_to_datetime(clean(tag(block, "pubDate")))).total_seconds() / 3600
        except Exception:
            pass
        items.append({"source": source, "title": t, "url": link, "desc": d,
                      "weight": weight, "pos": pos, "age": age_h})
    return items


def ok(it):
    text = it["title"] + " " + it["desc"]
    if BLOCK.search(text) or CLICKBAIT.search(it["title"]) or SKIP_URL.search(it["url"]):
        return False
    max_age = 168 if it["weight"] >= 3 else 72    # forsknings-/vitenskapskilder får en uke
    if it["age"] is not None and it["age"] > max_age:
        return False
    return True


def categorize(it):
    text = (it["title"] + " " + it["desc"]).lower()
    best, score = "Samfunn", 0
    for name, pts, pat in TOPICS:
        if re.search(r"\b(?:" + pat + ")", text):
            if pts > score:
                best, score = name, pts
    return best, score


def score(it):
    cat, topic = categorize(it)
    s = it["weight"] + topic
    if POSITIVE.search(it["title"]):
        s += 1
    if it["desc"]:
        s += 0.5
    s -= it["pos"] * 0.08                       # nyere saker står øverst i feeden
    if it["age"] is not None:
        s -= min(it["age"], 168) / 48           # minus et halvt poeng per døgn
    return s, cat


def collect(feeds):
    seen, out = set(), []
    for src, u, w in feeds:
        got = parse(src, u, w)
        kept = [it for it in got if ok(it)]
        print(f"  {src:15} {len(got):3} hentet, {len(kept):3} igjen  {u}")
        for it in got:
            if not ok(it):
                why = "blokk" if BLOCK.search(it["title"] + " " + it["desc"]) else "klikk" if CLICKBAIT.search(it["title"]) else "url" if SKIP_URL.search(it["url"]) else f"alder {it['age']:.0f}t"
                print(f"      x {why}: {it['title'][:90]}")
        for it in got:
            key = re.sub(r"\W", "", it["title"].lower())[:60]
            if key in seen or it["url"] in seen or not ok(it):
                continue
            seen.update([key, it["url"]])
            out.append(it)
    return out


def pick_rules(news, sport):
    for it in news:
        it["score"], it["category"] = score(it)
    news.sort(key=lambda x: -x["score"])
    stories, per_src, per_cat = [], {}, {}
    for it in news:
        if per_src.get(it["source"], 0) >= 3 or per_cat.get(it["category"], 0) >= 3:
            continue
        per_src[it["source"]] = per_src.get(it["source"], 0) + 1
        per_cat[it["category"]] = per_cat.get(it["category"], 0) + 1
        stories.append({"title": it["title"], "url": it["url"], "source": it["source"],
                        "category": it["category"], "summary": it["desc"], "why": ""})
        if len(stories) == 10:
            break
    if len(stories) < 10:                       # fyll opp uten grensene hvis det trengs
        have = {x["url"] for x in stories}
        for it in news:
            if it["url"] not in have and len(stories) < 10:
                stories.append({"title": it["title"], "url": it["url"], "source": it["source"],
                                "category": it["category"], "summary": it["desc"], "why": ""})
    best = None
    for it in sport:
        s = it["weight"] - it["pos"] * 0.1
        if re.search(r"norge|norsk|vm|ol|gull|sølv|bronse|seier|vant|rekord|historisk", it["title"], re.I):
            s += 2
        if not it["desc"]:
            s -= 1
        if best is None or s > best[0]:
            best = (s, it)
    sp = None
    if best:
        it = best[1]
        sp = {"title": it["title"], "url": it["url"], "source": it["source"], "summary": it["desc"]}
    return stories, sp


# ---------- Valgfritt: Claude (brukes bare hvis ANTHROPIC_API_KEY er lagt inn) ----------
PROMPT = """Du er redaktør for Gladnyheter.no, en norsk nyhetsforside uten negative nyheter.
Kast krig, kriminalitet, ulykker, skremsler, klikkagn, influensere, kjendisstoff, quiz og meninger.
Velg 10 interessante, lærerike eller viktige saker (forskning, teknologi, natur, kultur, næringsliv, nyttige samfunnssaker som ikke skremmer), maks 4 per kilde, viktigst først. Velg også 1 sportssak (helst norsk prestasjon).
For hver: informativ tittel på bokmål, oppsummering på 1-2 setninger basert KUN på teksten, category (Vitenskap, Medisin, Teknologi, Natur, Historie, Kultur, Økonomi, Næringsliv, Hverdag, Samfunn) og why (3-6 ord).
Svar KUN med JSON: {"stories":[{"id":0,"title":"","summary":"","category":"","why":""}],"sport":{"id":1000,"title":"","summary":""}}

NYHETER:
%s

SPORT:
%s
"""


def pick_claude(news, sport, key):
    fmt = lambda items, off: "\n".join(f"{i+off}. [{x['source']}] {x['title']} — {x['desc'][:120]}" for i, x in enumerate(items))
    news, sport = news[:80], sport[:25]
    body = json.dumps({"model": os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"), "max_tokens": 3000,
                       "messages": [{"role": "user", "content": PROMPT % (fmt(news, 0), fmt(sport, 1000))}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = "".join(b.get("text", "") for b in json.load(r)["content"])
    ans = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    stories, used = [], set()
    for s in ans.get("stories", []):
        i = int(s.get("id", -1))
        if 0 <= i < len(news) and i not in used:
            used.add(i)
            n = news[i]
            stories.append({"title": clean(s.get("title")) or n["title"], "url": n["url"], "source": n["source"],
                            "category": clean(s.get("category")) or "Samfunn",
                            "summary": clean(s.get("summary")) or n["desc"], "why": clean(s.get("why"))})
    sp, j = None, int((ans.get("sport") or {}).get("id", -1)) - 1000
    if 0 <= j < len(sport):
        x = ans["sport"]
        sp = {"title": clean(x.get("title")) or sport[j]["title"], "url": sport[j]["url"],
              "source": sport[j]["source"], "summary": clean(x.get("summary")) or sport[j]["desc"]}
    return stories[:10], sp


def main():
    news = collect(FEEDS)
    sport = collect(SPORT_FEEDS)
    print(f"{len(news)} nyheter og {len(sport)} sportssaker igjen etter filter")
    stories, sp = [], None
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            stories, sp = pick_claude(news, sport, key)
            print("Valgt av Claude")
        except Exception as e:
            print(f"Claude feilet ({e}) – bruker reglene", file=sys.stderr)
    if len(stories) < 6:
        stories, sp = pick_rules(news, sport)
        print("Valgt med regler")
    if len(stories) < 6:
        sys.exit("For få saker – beholder forrige utgave.")
    data = {"updated": datetime.datetime.now(OSLO).strftime("%Y-%m-%dT%H:%M"), "stories": stories}
    if sp:
        data["sport"] = sp
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for s in stories:
        print(f"- [{s['category']}] {s['title']} ({s['source']})")
    if sp:
        print(f"Sport: {sp['title']}")


if __name__ == "__main__":
    main()
