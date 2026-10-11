"""Gladnyheter: henter norske RSS-feeder, lar en AI velge dagens 10 beste saker + 1 sportssak,
og skriver resultatet til data.json. Kjøres hver time av GitHub Actions.

AI: Claude via secret ANTHROPIC_API_KEY (Settings > Secrets and variables > Actions).
"""
import json, os, re, sys, html, urllib.request, urllib.error, datetime
from zoneinfo import ZoneInfo

FEEDS = [
    ("NRK", "https://www.nrk.no/toppsaker.rss"),
    ("NRK", "https://www.nrk.no/viten/toppsaker.rss"),
    ("NRK", "https://www.nrk.no/kultur/toppsaker.rss"),
    ("NRK", "https://www.nrk.no/norge/toppsaker.rss"),
    ("forskning.no", "https://www.forskning.no/rss"),
    ("Gemini", "https://gemini.no/feed/"),
    ("E24", "https://e24.no/rss2/"),
    ("Aftenposten", "https://www.aftenposten.no/rss"),
    ("Aftenposten", "https://www.aftenposten.no/rss/kultur"),
    ("VG", "https://www.vg.no/rss/feed"),
    ("Teknisk Ukeblad", "https://www.tu.no/rss"),
]
SPORT_FEEDS = [
    ("NRK", "https://www.nrk.no/sport/toppsaker.rss"),
    ("VG", "https://www.vg.no/rss/feed/?categories=1072&limit=40"),
    ("Aftenposten", "https://www.aftenposten.no/rss/sport"),
]

# Grovfilter før AI-en (sparer plass). AI-en gjør den egentlige vurderingen.
BLOCK = re.compile(
    r"\b(krig|drept|drap|dødsfall|omkom|døde|skutt|knivstukket|terror|angrep|bombe|missil|rakett|"
    r"voldtekt|overgrep|siktet|tiltalt|fengslet|pågrepet|arrestert|politiet|ulykke|kollisjon|brann|"
    r"eksplo|katastrofe|jordskjelv|flom|skred|gaza|ukraina|russland|putin|israel|hamas|iran|"
    r"selvmord|kreftsyk|trump|influenser|kjendis|instagram|tiktok|reality|«paradise|quiz|kryssord|"
    r"se bildene|se video|se høydepunkt|høydepunktene|på \d+ minutter|tegneserie|dagens lunch|dagens dunce)",
    re.I,
)

UA = {"User-Agent": "Mozilla/5.0 (Gladnyheter.no RSS-leser)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def clean(s, n=None):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] if n else s


def strip_utm(u):
    return re.sub(r"[?&]utm_[^&#]+", "", u or "").rstrip("?&")


def parse(source, url, limit):
    items = []
    try:
        raw = fetch(url).decode("utf-8", "replace")
    except Exception as e:
        print(f"Feil: {url}: {e}", file=sys.stderr)
        return items
    def tag(block, name):
        m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
        v = m.group(1) if m else ""
        return re.sub(r"^\s*<!\[CDATA\[(.*?)\]\]>\s*$", r"\1", v, flags=re.S)
    for block in re.findall(r"<item[\s>].*?</item>", raw, re.S):
        t = clean(tag(block, "title"))
        link = strip_utm(clean(tag(block, "link")))
        d = clean(tag(block, "description"), 120)
        if not t or not link:
            continue
        items.append({"source": source, "title": t, "url": link, "desc": d})
        if len(items) >= limit:
            break
    return items


def collect(feeds, limit, maxn):
    seen, out = set(), []
    for src, u in feeds:
        for it in parse(src, u, limit):
            key = it["url"].split("?")[0]
            if key in seen or BLOCK.search(it["title"] + " " + it["desc"]):
                continue
            seen.add(key)
            out.append(it)
    return out[:maxn]


PROMPT = """Du er redaktør for Gladnyheter.no, en norsk nyhetsforside for en voksen leser som er lei av negative nyheter.

KAST: krig, terror, konflikter, kriminalitet, ulykker, katastrofer, skremselsnyheter og alt som bare gjør leseren nedstemt uten at hen kan gjøre noe med det. Kast også klikkagn (vage eller lokkende titler), influensere, kjendisstoff, reality, sladder, quiz, kommentarer og meningsinnlegg.

VELG 10 saker som er interessante, lærerike eller viktige. Leseren liker: forskning og teknologi; natur, dyr og miljøløsninger; kultur og underholdning (film, bøker, tegneserier, musikk); næringsliv, gründere og netthandel. Nyttige samfunnssaker som påvirker hverdagen (rente, prisvekst, streik avverget, nye regler, statsbudsjett) skal med når de ikke er skremmende. Spre utvalget over tema og kilder (maks 4 fra samme kilde). Viktigste/mest interessante sak først.

VELG også 1 sportssak: den viktigste norske sportsnyheten nå, helst en norsk prestasjon (ikke bråk eller skandaler). Velg fra sportslisten.

For hver sak: skriv en klar, informativ tittel på norsk bokmål (omskriv klikkagn), en oppsummering på 1-2 setninger som BARE bygger på tittel og beskrivelse (ikke dikt opp fakta), category (én av: Vitenskap, Medisin, Teknologi, Natur, Historie, Kultur, Økonomi, Næringsliv, Hverdag, Samfunn) og why (3-6 ord om hvorfor saken er valgt).

Svar KUN med JSON:
{"stories":[{"id":<nummer>,"title":"","summary":"","category":"","why":""}],"sport":{"id":<nummer>,"title":"","summary":""}}

NYHETER:
%s

SPORT:
%s
"""


def fmt(items, offset=0):
    return "\n".join(
        f"{i+offset}. [{it['source']}] {it['title']} — {it['desc']}" for i, it in enumerate(items)
    )


def ask_claude(prompt, key):
    body = json.dumps({
        "model": os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"),
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Claude API svarte {e.code}: {e.read()[:800]!r}")
    return "".join(b.get("text", "") for b in res["content"])




def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Ingen ANTHROPIC_API_KEY lagt inn ennå – beholder forrige utgave.")
        return
    news = collect(FEEDS, 15, 80)
    sport = collect(SPORT_FEEDS, 20, 25)
    print(f"{len(news)} nyheter, {len(sport)} sport etter grovfilter")
    if len(news) < 10:
        sys.exit("For få saker – beholder forrige utgave.")
    prompt = PROMPT % (fmt(news), fmt(sport, 1000))
    key = os.environ.get("ANTHROPIC_API_KEY")
    raw = ask_claude(prompt, key)
    m = re.search(r"\{.*\}", raw, re.S)
    ans = json.loads(m.group(0))

    stories, used = [], set()
    for s in ans.get("stories", []):
        i = int(s.get("id", -1))
        if 0 <= i < len(news) and i not in used:
            used.add(i)
            src = news[i]
            stories.append({
                "title": clean(s.get("title")) or src["title"], "url": src["url"], "source": src["source"],
                "category": clean(s.get("category")) or "Samfunn", "summary": clean(s.get("summary")) or src["desc"],
                "why": clean(s.get("why")),
            })
    if len(stories) < 6:
        sys.exit("AI-svaret hadde for få gyldige saker – beholder forrige utgave.")
    data = {
        "updated": datetime.datetime.now(ZoneInfo("Europe/Oslo")).strftime("%Y-%m-%dT%H:%M"),
        "stories": stories[:10],
    }
    sp = ans.get("sport") or {}
    j = int(sp.get("id", -1)) - 1000
    if 0 <= j < len(sport):
        data["sport"] = {"title": clean(sp.get("title")) or sport[j]["title"], "url": sport[j]["url"],
                         "source": sport[j]["source"], "summary": clean(sp.get("summary")) or sport[j]["desc"]}
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("Toppsak:", data["stories"][0]["title"])


if __name__ == "__main__":
    main()
