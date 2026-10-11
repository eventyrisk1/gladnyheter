"""Gladnyheter: henter norske RSS-feeder, velger topp 3 saker i hver kategori
og skriver resultatet til data.json. Kjøres hver time av GitHub Actions (gratis).

Utvalget gjøres av Gemini (gratis, secret GEMINI_API_KEY). Finnes ANTHROPIC_API_KEY brukes
Claude. Uten nøkkel, eller hvis AI-en feiler, brukes faste regler (filter + poeng) som reserve.
"""
import json, os, re, sys, html, urllib.request, urllib.error, datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")

# (kilde, url, kildepoeng)
FEEDS = [
    ("Utdanningsnytt", "https://www.utdanningsnytt.no/?lab_viewport=rss", 2),
    ("Psykologisk.no", "https://psykologisk.no/feed/", 2),
    ("Vårt Land", "https://www.vl.no/?lab_viewport=rss", 1),
    ("Kunstkritikk", "https://kunstkritikk.no/feed/", 2),
    ("Ballade", "https://www.ballade.no/feed", 2),
    ("Gamer.no", "https://www.gamer.no/rss", 2),
    ("forskning.no", "https://www.forskning.no/?lab_viewport=rss", 2),
    ("Gemini", "https://gemini.no/feed/", 2),
    ("NRK", "https://www.nrk.no/viten/toppsaker.rss", 2),
    ("NRK", "https://www.nrk.no/kultur/toppsaker.rss", 2),
    ("Teknisk Ukeblad", "https://www.tu.no/rss", 1),
    ("Aftenposten", "https://www.aftenposten.no/rss/kultur", 2),
    ("E24", "https://e24.no/rss2/", 1),
    ("NRK", "https://www.nrk.no/toppsaker.rss", 1),
    ("NRK", "https://www.nrk.no/norge/toppsaker.rss", 1),
    ("Aftenposten", "https://www.aftenposten.no/rss", 1),
    ("VG", "https://www.vg.no/rss/feed", 1),
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
    r"brann|eksplo|katastrofe|dommedag|undergang|jordskjelv|flom|skred|\bras\b|storm|uvær|gaza|ukraina|russland|putin|israel|hamas|"
    r"iran|nato|atomvåpen|atomkraftulykke|selvmord|kreft(?!fri)|opereres|operasjon|sykehus|svulst|diagnose|\bsyke?\b|pasient|sykdom|smitte|pandemi|trump|influenser|kjendis|instagram|tiktok|reality|"
    r"paradise hotel|farmen|skal vi danse|quiz|kryssord|se bildene|se video|høydepunkt|på \d+ minutter|"
    r"tegneserie|dagens lunch|dagens dunce|konkurs|permitter|nedlegg|kutt|streik(?! avverget)|savnet|"
    r"alarm|frykt|advar|trussel|sjokk|skandale|rase|raste|slakt|knus|bråk|krangel|rettssak|søksmål|saksøk|"
    r"etterforsk|anklag|mistenkt|sikkerhetsbrudd|hacker|svindel|bedrag|rasis|hets\b|hat\b|hatet|mobb|demonstr|protest|annonse|sponset|reklame|i samarbeid med|annonsørinnhold)",
    re.I,
)
# Klikkagn-mønstre i titler
CLICKBAIT = re.compile(
    r"(\(\d{1,3}\)|^–|^-|: –|: -|dette er|her er|sjekk|dette skjedde|du vil|du må|ikke tro|avslør|hemmelig|"
    r"utrolig|vanvittig|helt rå|alle snakker|reagerer|hylles|får kritikk|tar et oppgjør|går til angrep|"
    r"ber om unnskyldning|bryter tausheten|åpner opp|forteller om|mener at|kommentar|debatt|leder:)",
    re.I,
)
# Opinion/kommentar i URL
SKIP_URL = re.compile(r"/(video|kommentar|debatt|meninger|leder|kronikk|ytring|quiz|tegneserier|hjernetrim)/", re.I)

TOPICS = [
    ("Spill", 3, r"dataspill|brettspill|spillet\b|gaming|playstation|xbox|nintendo|sjakk|puslespill|kryssord|hobby|strikk|modellbygg|modelljernbane|lego|fotografer|frimerke"),
    ("KI", 4, r"kunstig intelligens|\bki\b|chatgpt|språkmodell|\bai\b"),
    ("Psykologi", 3, r"psykolog|følelse|tanke|hjernen|atferd|personlighet|lykke|søvn|stress|motivasjon"),
    ("Oppvekst", 3, r"barnehage|skole|elev|lærer|foreld|oppdragelse|ungdom|barn\b|barna"),
    ("Aand", 3, r"meditasjon|mindfulness|pilegrim|spiritu|stillhet|indre ro|yoga|filosof|livsvisdom|ettertanke"),
    ("Tro", 3, r"kirke|tro\b|religion|prest|bibel|menighet|biskop|livssyn|islam|kristen"),
    ("Kunst", 3, r"kunst|maleri|utstilling|galleri|kunstner|museum"),
    ("Musikk", 3, r"musikk|album|konsert|låt|band|artist|sanger|komponist|festival"),
    ("Litteratur", 3, r"\bbok\b|bøker|roman|forfatter|litteratur|lyrikk|dikt"),
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


def parse(source, url, weight, limit=20):
    items = []
    try:
        raw = fetch(url).decode("utf-8", "replace")
    except Exception as e:
        print(f"Feil: {url}: {e}", file=sys.stderr)
        return items
    now = datetime.datetime.now(datetime.timezone.utc)
    blocks = re.findall(r"<item[\s>].*?</item>", raw, re.S) or re.findall(r"<entry[\s>].*?</entry>", raw, re.S)
    if not blocks:
        print(f"      ingen saker funnet, starten av svaret: {raw[:300]!r}")
    for pos, block in enumerate(blocks[:limit]):
        t = clean(tag(block, "title"))
        link = clean(tag(block, "link"))
        if not link:
            m = re.search(r'<link[^>]*href="([^"]+)"', block)
            link = html.unescape(m.group(1)) if m else ""
        link = strip_utm(link)
        d = clean(tag(block, "description") or tag(block, "summary") or tag(block, "content"), 220)
        if not t or not link:
            continue
        age_h = None
        try:
            age_h = (now - parsedate_to_datetime(clean(tag(block, "pubDate")))).total_seconds() / 3600
        except Exception:
            try:
                ds = clean(tag(block, "updated") or tag(block, "published") or tag(block, "dc:date"))
                age_h = (now - datetime.datetime.fromisoformat(ds.replace("Z", "+00:00"))).total_seconds() / 3600
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
    # Fordel kildene jevnt (annenhver sak fra hver kilde), så ingen kilde dominerer listen
    groups = {}
    for it in out:
        groups.setdefault(it["source"], []).append(it)
    mixed = []
    while any(groups.values()):
        for g in groups.values():
            if g:
                mixed.append(g.pop(0))
    return mixed


CATS = [
    ("samfunn", "Samfunn", "nyttige samfunnssaker og hverdag: nye regler, streik avverget, transport, lokalsamfunn, gode initiativ"),
    ("okonomi", "Økonomi og næringsliv", "rente, prisvekst, bolig, strøm, gründere, bedrifter, netthandel, handel"),
    ("vitenskap", "Vitenskap og teknologi", "forskning, oppdagelser, verdensrommet, medisinske fremskritt, ny teknologi (ikke KI)"),
    ("ki", "Kunstig intelligens", "nyheter om KI, språkmodeller og hvordan KI brukes"),
    ("natur", "Natur og miljø", "dyr, natur, friluftsliv, miljøløsninger, klimaløsninger"),
    ("psykologi", "Psykologi", "psykologi, hjernen, følelser, relasjoner, livsmestring"),
    ("oppvekst", "Barn og oppvekst", "barnehage, skole, utdanning, oppdragelse, foreldre, ungdom"),
    ("tro", "Tro og livssyn", "tro, religion, kirke, livssyn, etikk – det som samler, ikke konflikter"),
    ("aand", "Ånd og spiritualitet", "meditasjon, mindfulness, stillhet, pilegrimsvandring, filosofi, meningen med livet og indre ro – ikke alternativ behandling, healing eller overtro"),
    ("kunst", "Kunst", "billedkunst, utstillinger, museer, design, arkitektur"),
    ("musikk", "Musikk", "musikk, artister, album, konserter"),
    ("litteratur", "Litteratur", "bøker, forfattere, litteratur, lesing"),
    ("kultur", "Film, scene og historie", "film, serier, teater, dans, arkeologi og historie"),
    ("spill", "Spill og hobby", "dataspill, brettspill, sjakk, puslespill, LEGO og hobbyer som strikking, modellbygging, foto og samling – nye spill, gode tips og morsomme prosjekter, ikke bransjedrama"),
    ("sport", "Sport", "norske prestasjoner og viktige sportsnyheter (kun fra SPORT-listen)"),
]
RULE_MAP = {"Samfunn": "samfunn", "Hverdag": "samfunn", "Økonomi": "okonomi", "Næringsliv": "okonomi",
            "Vitenskap": "vitenskap", "Medisin": "vitenskap", "Teknologi": "vitenskap", "KI": "ki",
            "Natur": "natur", "Psykologi": "psykologi", "Oppvekst": "oppvekst", "Tro": "tro", "Aand": "aand",
            "Kunst": "kunst", "Musikk": "musikk", "Litteratur": "litteratur",
            "Kultur": "kultur", "Historie": "kultur", "Spill": "spill"}


def story(it, title=None, summary=None):
    return {"title": clean(title) or it["title"], "url": it["url"], "source": it["source"],
            "summary": clean(summary) or it["desc"]}


def pick_rules(news, sport):
    for it in news:
        it["score"], it["category"] = score(it)
    news.sort(key=lambda x: -x["score"])
    out = {cid: [] for cid, _, _ in CATS}
    for it in news:
        cid = RULE_MAP.get(it["category"], "samfunn")
        if len(out[cid]) < 3:
            out[cid].append(story(it))
    def sport_score(it):
        s = it["weight"] - it["pos"] * 0.1
        if re.search(r"norge|norsk|vm|ol|gull|sølv|bronse|seier|vant|rekord|historisk", it["title"], re.I):
            s += 2
        if not it["desc"]:
            s -= 1
        return s
    out["sport"] = [story(it) for it in sorted(sport, key=lambda x: -sport_score(x))[:3]]
    return out


PROMPT = """Du er redaktør for Gladnyheter.com, en norsk nyhetsforside uten negative nyheter.
Leserne er voksne nordmenn som er lei av negative nyheter.
KAST ALT som handler om krig, militære konflikter, forsvar/våpen, terror, kriminalitet, ulykker, sykdom, død, katastrofer, kriser og skremsler, og alt som bare gjør leseren nedstemt uten at hen kan gjøre noe med det. Kast også klikkagn, reklame, sponset innhold, annonsørinnhold, influensere, kjendisstoff, reality, sladder, quiz, kommentarer og meningsinnlegg.

Velg de 3 mest interessante, lærerike eller viktige sakene i HVER av disse kategoriene (viktigst først):
%s
Regler: Samme sak kan bare brukes én gang. Sport velges bare fra SPORT-listen, de andre kategoriene bare fra NYHETER-listen. Spre på kildene: høyst 1 sak fra samme kilde i hver kategori, og høyst 4 saker fra samme kilde totalt. Bruk gjerne mange ulike kilder (NRK, Aftenposten, VG, E24, fagkilder osv.). Finnes det færre enn 3 gode saker i en kategori, ta med færre heller enn dårlige saker.
For hver sak: informativ tittel på bokmål (omskriv klikkagn) og en oppsummering på 1-2 setninger som BARE bygger på teksten (ikke dikt opp fakta).
Svar KUN med JSON der hver kategori-id er en nøkkel, f.eks.: {"samfunn":[{"id":0,"title":"","summary":""}],"okonomi":[...], ... ,"sport":[{"id":1000,"title":"","summary":""}]}

NYHETER:
%s

SPORT:
%s
"""


def build_prompt(news, sport):
    fmt = lambda items, off: "\n".join(f"{i+off}. [{x['source']}] {x['title']} — {x['desc'][:150]}" for i, x in enumerate(items))
    cats = "\n".join(f"- {cid}: {name} ({desc})" for cid, name, desc in CATS)
    return PROMPT % (cats, fmt(news, 0), fmt(sport, 1000))


def read_answer(raw, news, sport):
    ans = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    out, used, per_src = {}, set(), {}
    for cid, _, _ in CATS:
        out[cid] = []
        for s in ans.get(cid, []) or []:
            try:
                i = int(s.get("id", -1))
            except Exception:
                continue
            pool, j = (sport, i - 1000) if cid == "sport" else (news, i)
            if 0 <= j < len(pool) and i not in used and len(out[cid]) < 3:
                src = pool[j]["source"]
                if any(x["source"] == src for x in out[cid]) or per_src.get(src, 0) >= MAX_PER_SOURCE:
                    continue
                used.add(i)
                per_src[src] = per_src.get(src, 0) + 1
                out[cid].append(story(pool[j], s.get("title"), s.get("summary")))
    return out


MAX_PER_SOURCE = 4

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemini-2.0-flash"]


def pick_gemini(news, sport, key):
    news, sport = news[:170], sport[:30]
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": build_prompt(news, sport)}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }).encode()
    last = None
    for model in [os.environ.get("GEMINI_MODEL")] + GEMINI_MODELS:
        if not model:
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.load(r)
            raw = "".join(p.get("text", "") for p in res["candidates"][0]["content"]["parts"])
            print(f"Gemini-modell: {model}")
            return read_answer(raw, news, sport)
        except urllib.error.HTTPError as e:
            last = f"{model}: {e.code} {e.read()[:300]!r}"
            print(f"  {last}", file=sys.stderr)
        except Exception as e:
            last = f"{model}: {e}"
            print(f"  {last}", file=sys.stderr)
    raise RuntimeError(last)


def pick_claude(news, sport, key):
    news, sport = news[:150], sport[:25]
    body = json.dumps({"model": os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"), "max_tokens": 8000,
                       "messages": [{"role": "user", "content": build_prompt(news, sport)}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = "".join(b.get("text", "") for b in json.load(r)["content"])
    return read_answer(raw, news, sport)


def count(out):
    return sum(len(v) for v in (out or {}).values())


# ---------- «Nyttig i dag»: strømpris (hvakosterstrommen.no) og vær (Meteorologisk institutt) ----------
AREAS = [  # id, navn, prisområde, lat, lon
    ("oslo", "Oslo / Østlandet", "NO1", 59.91, 10.75),
    ("kristiansand", "Kristiansand / Sørlandet", "NO2", 58.15, 8.00),
    ("trondheim", "Trondheim / Midt-Norge", "NO3", 63.43, 10.40),
    ("tromso", "Tromsø / Nord-Norge", "NO4", 69.65, 18.96),
    ("bergen", "Bergen / Vestlandet", "NO5", 60.39, 5.32),
    ("stavanger", "Stavanger / Rogaland", "NO2", 58.97, 5.73),
]


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def power_prices(zone, day):
    """Timepriser i øre/kWh inkl. mva (NO4 har ikke mva). Returnerer [[HH:MM, øre], ...]."""
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{day:%Y}/{day:%m-%d}_{zone}.json"
    vat = 1.0 if zone == "NO4" else 1.25
    rows = get_json(url)
    return [[r["time_start"][11:16], round(r["NOK_per_kWh"] * 100 * vat, 1)] for r in rows]


def weather(lat, lon, today):
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
    d = get_json(url, {"User-Agent": "gladnyheter.com https://gladnyheter.com"})
    ts = d["properties"]["timeseries"]
    now = ts[0]
    temps = [t["data"]["instant"]["details"]["air_temperature"] for t in ts
             if datetime.datetime.fromisoformat(t["time"].replace("Z", "+00:00")).astimezone(OSLO).date() == today]
    n6 = now["data"].get("next_6_hours") or now["data"].get("next_1_hours") or {}
    n12 = now["data"].get("next_12_hours") or {}
    return {
        "temp": round(now["data"]["instant"]["details"]["air_temperature"]),
        "min": round(min(temps)) if temps else None,
        "max": round(max(temps)) if temps else None,
        "symbol": (n12.get("summary") or n6.get("summary") or {}).get("symbol_code", ""),
        "rain6": (n6.get("details") or {}).get("precipitation_amount"),
    }


def useful_today():
    now = datetime.datetime.now(OSLO)
    out = {"areas": [], "power": {}, "power_tomorrow": {}, "weather": {}}
    for aid, name, zone, lat, lon in AREAS:
        out["areas"].append({"id": aid, "name": name, "zone": zone})
        if zone not in out["power"]:
            try:
                out["power"][zone] = power_prices(zone, now)
            except Exception as e:
                print(f"Strømpris {zone} feilet: {e}", file=sys.stderr)
            if now.hour >= 14:
                try:
                    out["power_tomorrow"][zone] = power_prices(zone, now + datetime.timedelta(days=1))
                except Exception:
                    pass
        try:
            out["weather"][aid] = weather(lat, lon, now.date())
        except Exception as e:
            print(f"Vær {aid} feilet: {e}", file=sys.stderr)
    out["date"] = now.strftime("%Y-%m-%d")
    return out


def main():
    news = collect(FEEDS)
    sport = collect(SPORT_FEEDS)
    print(f"{len(news)} nyheter og {len(sport)} sportssaker igjen etter filter")
    out = None
    for name, env, fn in [("Claude", "ANTHROPIC_API_KEY", pick_claude), ("Gemini", "GEMINI_API_KEY", pick_gemini)]:
        key = os.environ.get(env)
        if key and count(out) < 15:
            try:
                out = fn(news, sport, key)
                print(f"Valgt av {name}")
            except Exception as e:
                print(f"{name} feilet ({e})", file=sys.stderr)
    if count(out) < 15:
        out = pick_rules(news, sport)
        print("Valgt med regler")
    if count(out) < 12:
        sys.exit("For få saker – beholder forrige utgave.")
    data = {"updated": datetime.datetime.now(OSLO).strftime("%Y-%m-%dT%H:%M"),
            "categories": [{"id": cid, "name": name, "stories": out.get(cid, [])} for cid, name, _ in CATS]}
    try:
        data["today"] = useful_today()
    except Exception as e:
        print(f"«Nyttig i dag» feilet: {e}", file=sys.stderr)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for c in data["categories"]:
        print(f"{c['name']}:")
        for s in c["stories"]:
            print(f"  - {s['title']} ({s['source']})")


if __name__ == "__main__":
    main()
