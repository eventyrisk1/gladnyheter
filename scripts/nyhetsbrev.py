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
import urllib.request
from zoneinfo import ZoneInfo

KEY = os.environ.get("BREVO_API_KEY", "").strip()
BD_KEY = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
LIST_ID = os.environ.get("BREVO_LIST_ID", "").strip()
FORCE = os.environ.get("FORCE", "") == "true"
TEST_TO = os.environ.get("TEST_TO", "").strip()  # sender kun test til denne adressen
SENDER = {"name": "Gladnyheter", "email": os.environ.get("BREVO_SENDER", "post@eventyrisk.no")}
SITE = "https://gladnyheter.com/"
DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
          "september", "oktober", "november", "desember"]


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


def build(data, now, unsub=True):
    e = html.escape
    date = f"{DAYS[now.weekday()]} {now.day}. {MONTHS[now.month - 1]}"
    total = sum(len(c["stories"]) for c in data["categories"])
    items = ""
    for i, (cat, s) in enumerate(pick(data), 1):
        items += f"""
<tr><td style="padding:18px 0;border-top:1px solid #e3e9e5">
  <div style="font:600 12px/1.4 Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#2c6a86">{i}. {e(cat)}</div>
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
  {'<a href="{{ unsubscribe }}" style="color:#7a8680">Meld deg av</a>' if unsub else ''}
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
    first = pick(data)[0][1]["title"]
    try:
        camp = api("/emailCampaigns", {
            "name": f"Dagens 5 gode {now:%Y-%m-%d}",
            "subject": f"☀️ {first}",
            "previewText": "Dagens 5 gode nyheter – på to minutter.",
            "sender": SENDER,
            "htmlContent": build(data, now),
            "recipients": {"listIds": [int(LIST_ID)]},
        })
        if TEST_TO:
            api(f"/emailCampaigns/{camp['id']}/sendTest", {"emailTo": [TEST_TO]})
            print(f"Testutsending til {TEST_TO}: kampanje {camp['id']} – «{first}»")
            return
        api(f"/emailCampaigns/{camp['id']}/sendNow", {})
        print(f"Sendt: kampanje {camp['id']} – «{first}»")
    except urllib.error.HTTPError as e:
        print("Feil fra Brevo:", e.code, e.read().decode()[:500])
        sys.exit(1)


if __name__ == "__main__":
    main()
