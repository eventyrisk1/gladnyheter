"""Sender «Dagens 5 gode» på e-post kl. 07 (norsk tid) via Buttondown eller Brevo.

Brevo (foretrukket): GitHub-secrets
  BREVO_API_KEY  – API-nøkkel fra Brevo (Settings → SMTP & API → API keys)
  BREVO_LIST_ID  – ID-en til kontaktlisten påmeldingene havner i (tall)
Buttondown (reserve): GitHub-secret BUTTONDOWN_API_KEY – brukes bare hvis Brevo mangler.
Uten noen av disse hopper skriptet stille over.
"""
import datetime
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

KEY = os.environ.get("BREVO_API_KEY", "").strip()
BD_KEY = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
LIST_ID = os.environ.get("BREVO_LIST_ID", "").strip()
FORCE = os.environ.get("FORCE", "") == "true"
TEST_TO = os.environ.get("TEST_TO", "").strip()  # sender kun test til denne adressen
SENDER = {"name": "Gladnyheter", "email": os.environ.get("BREVO_SENDER", "post@eventyrisk.no")}
SITE = "https://gladnyheter.com/"
UNSUB_URL = "https://gladnyheter.com/avmeld?e={{ params.EMAIL }}"
DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
          "september", "oktober", "november", "desember"]


def pick_for(data, ids, n=5):
    """Dagens beste sak fra hver valgt kategori (i abonnentens rekkefølge), fylt opp til n."""
    by = {c["id"]: c for c in data["categories"]}
    ids = [i for i in ids if i in by][:n]
    lists = {i: [s for s in by[i]["stories"] if not s.get("paid")] for i in ids}
    taken = {i: 0 for i in ids}
    count = 0
    for rnd in range(2):  # høyst to saker fra samme kategori
        for i in ids:
            if count < n and len(lists[i]) > rnd:
                taken[i] += 1
                count += 1
    out = [(by[i]["name"], s) for i in ids for s in lists[i][:taken[i]]]
    # Fyll opp med dagens beste fra andre kategorier hvis abonnentens kategorier er tynne i dag
    for c in data["categories"]:
        if len(out) >= n:
            break
        if c["id"] not in ids and c["id"] != "sport":
            free = [s for s in c["stories"] if not s.get("paid")]
            if free:
                out.append((c["name"], free[0]))
    return out


def cats_of(contact, data):
    raw = str((contact.get("attributes") or {}).get("KATEGORIER") or "")
    valid = {c["id"] for c in data["categories"]}
    ids = [x.strip() for x in raw.split(",") if x.strip() in valid]
    return ids or [c["id"] for c in data["categories"] if c["id"] != "sport" and c["stories"]][:5]


def pick(data, n=5):
    """Én sak fra hver av de første kategoriene, helst fra ulike kilder."""
    out, used_src = [], set()
    cats = [c for c in data["categories"] if c["id"] != "sport" and c["stories"]]
    for strict in (True, False):
        for c in cats:
            if len(out) >= n:
                break
            if any(o[0] == c["name"] for o in out):
                continue
            for s in c["stories"]:
                if s.get("paid") or (strict and s["source"] in used_src):
                    continue
                out.append((c["name"], s))
                used_src.add(s["source"])
                break
    return out[:n]


def build(data, now, unsub=True, picks=None):
    e = html.escape
    date = f"{DAYS[now.weekday()]} {now.day}. {MONTHS[now.month - 1]}"
    total = sum(len(c["stories"]) for c in data["categories"])
    items = ""
    prev = None
    for i, (cat, s) in enumerate(picks or pick(data), 1):
        label = ("Mer fra " if cat == prev else "") + cat
        prev = cat
        items += f"""
<tr><td style="padding:18px 0;border-top:1px solid #e3e9e5">
  <div style="font:600 12px/1.4 Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#2c6a86">{i}. {e(label)}</div>
  <a href="{e(s['url'])}" style="display:block;margin:6px 0 6px;font:700 20px/1.3 Georgia,serif;color:#1d2a25;text-decoration:none">{e(s['title'])}</a>
  <div style="font:16px/1.55 Georgia,serif;color:#3d4642">{e(s.get('summary', ''))}</div>
  <div style="margin-top:6px;font:13px/1.4 Arial,sans-serif;color:#7a8680">{e(s['source'])}</div>
</td></tr>"""
    return f"""<!doctype html><html lang="nb"><body style="margin:0;background:#f2f5f1">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f5f1"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:16px;padding:28px">
<tr><td style="padding:0 0 14px;border-bottom:3px solid #1d2a25">
  <div style="font:800 30px/1 Arial,sans-serif;color:#1d2a25;letter-spacing:-.02em"><span style="color:#e9a923">●</span> Gladnyheter</div>
  <div style="margin-top:8px;font:14px/1.4 Arial,sans-serif;color:#5d6b64">Dagens 5 gode · {e(date)}</div>
</td></tr>
{items}
<tr><td style="padding:22px 0 8px;border-top:1px solid #e3e9e5;text-align:center">
  <a href="{SITE}" style="display:inline-block;background:#1d2a25;color:#ffffff;font:700 16px/1 Arial,sans-serif;padding:14px 22px;border-radius:999px;text-decoration:none">Se alle {total} sakene på gladnyheter.com</a>
</td></tr>
<tr><td style="padding:18px 0 0;text-align:center;font:13px/1.5 Arial,sans-serif;color:#7a8680">
  Kjenner du noen som trenger en lysere morgen? Videresend denne e-posten.<br><br>
  Gladnyheter velger sakene automatisk fra norske nyhetskilder. <a href="{SITE}om" style="color:#2c6a86">Slik fungerer det</a><br>
  <a href="{SITE}#gn-nl" style="color:#2c6a86">Endre kategoriene dine</a>{(' · <a href="' + e(unsub) + '" style="color:#7a8680">Meld deg av</a>') if isinstance(unsub, str) else ('<br><a href="{{ unsubscribe }}" style="color:#7a8680">Meld deg av</a>' if unsub else '')}
</td></tr>
</table></td></tr></table></body></html>"""


def api(path, body):
    req = urllib.request.Request("https://api.brevo.com/v3" + path, data=json.dumps(body).encode(),
                                 headers={"api-key": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def send_buttondown(data, now):
    first = pick(data)[0][1]["title"]
    body = "<!-- buttondown-editor-mode: fancy -->\n" + build(data, now, unsub=False)
    req = urllib.request.Request("https://api.buttondown.com/v1/emails", data=json.dumps({
        "subject": f"☀️ {first}", "body": body, "status": "about_to_send"}).encode(),
        headers={"Authorization": "Token " + BD_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Sendt via Buttondown:", r.status, f"«{first}»")
    except urllib.error.HTTPError as e:
        print("Feil fra Buttondown:", e.code, e.read().decode()[:500])
        sys.exit(1)


def main():
    if BD_KEY and not (KEY and LIST_ID):
        now = datetime.datetime.now(ZoneInfo("Europe/Oslo"))
        if not FORCE and now.hour != 7:
            print(f"Klokka er {now:%H:%M} i Norge – ikke utsendingstid.")
            return
        data = json.load(open("data.json", encoding="utf-8"))
        if len(pick(data)) < 3:
            print("For få saker – sender ikke i dag.")
            return
        return send_buttondown(data, now)
    if not KEY or not LIST_ID:
        print("Mangler BREVO_API_KEY eller BREVO_LIST_ID – hopper over nyhetsbrevet.")
        return
    now = datetime.datetime.now(ZoneInfo("Europe/Oslo"))
    if not FORCE and not TEST_TO and now.hour != 7:
        print(f"Klokka er {now:%H:%M} i Norge – ikke utsendingstid.")
        return
    data = json.load(open("data.json", encoding="utf-8"))
    if len(pick(data)) < 3:
        print("For få saker – sender ikke i dag.")
        return
    try:
        send_personal(data, now)
    except urllib.error.HTTPError as e:
        print("Feil fra Brevo:", e.code, e.read().decode()[:500])
        sys.exit(1)


def get(path):
    req = urllib.request.Request("https://api.brevo.com/v3" + path,
                                 headers={"api-key": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def contacts():
    out, off = [], 0
    while True:
        page = get(f"/contacts/lists/{int(LIST_ID)}/contacts?limit=500&offset={off}")
        cs = page.get("contacts", [])
        out += cs
        off += len(cs)
        if not cs or off >= page.get("count", 0):
            return out


def send_personal(data, now):
    if TEST_TO:
        try:
            people = [get("/contacts/" + urllib.parse.quote(TEST_TO))]
        except urllib.error.HTTPError:
            people = [{"email": TEST_TO, "attributes": {}}]
    else:
        lid = int(LIST_ID)
        people = [c for c in contacts() if not c.get("emailBlacklisted") and lid not in (c.get("listUnsubscribed") or [])]
    groups = {}
    for c in people:
        groups.setdefault(tuple(cats_of(c, data)), []).append(c["email"])
    versions = []
    for ids, emails in groups.items():
        picks = pick_for(data, list(ids))
        if len(picks) < 3:
            picks = pick(data)
        html_ = build(data, now, unsub=UNSUB_URL, picks=picks)
        subject = ("TEST - " if TEST_TO else "") + f"☀️ {picks[0][1]['title']}"
        for em in emails:
            versions.append({"to": [{"email": em}], "subject": subject, "htmlContent": html_, "params": {"EMAIL": em}})
    for k in range(0, len(versions), 500):
        chunk = versions[k:k + 500]
        api("/smtp/email", {"sender": SENDER, "subject": chunk[0]["subject"], "htmlContent": chunk[0]["htmlContent"],
                            "messageVersions": chunk, "tags": ["dagens5"],
                            "headers": {"List-Unsubscribe": "<mailto:post@eventyrisk.no?subject=Meld%20av>"}})
    print(f"Sendt til {len(versions)} mottaker(e) i {len(groups)} kategorivariant(er)" + (f" (test til {TEST_TO})" if TEST_TO else ""))

if __name__ == "__main__":
    main()
