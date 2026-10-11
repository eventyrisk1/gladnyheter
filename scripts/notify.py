"""Sender push-varsel via OneSignal kl. 7 og 16 (norsk tid) med en gladnyhet fra data.json."""
import datetime
import json
import os
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

KEY = os.environ.get("ONESIGNAL_API_KEY", "").strip()
FORCE = os.environ.get("FORCE", "") == "true"


def main():
    m = re.search(r'var OS_APP\s*=\s*"([^"]*)"', open("index.html", encoding="utf-8").read())
    app = m.group(1) if m else ""
    if not KEY or not app:
        print("Mangler OneSignal-nøkkel eller app-id – hopper over varsel.")
        return
    now = datetime.datetime.now(ZoneInfo("Europe/Oslo"))
    if not FORCE and now.hour not in (7, 16):
        print(f"Klokka er {now:%H:%M} i Norge – ikke varseltid.")
        return
    data = json.load(open("data.json", encoding="utf-8"))
    cats = [c for c in data["categories"] if c["id"] != "sport" and c["stories"]]
    if not cats:
        print("Ingen saker.")
        return
    cat = cats[(now.timetuple().tm_yday * 2 + (now.hour >= 12)) % len(cats)]
    title = cat["stories"][0]["title"]
    total = sum(len(c["stories"]) for c in data["categories"])
    head = "God morgen! Dagens gladnyheter" if now.hour < 12 else "Nye gladnyheter i ettermiddag"
    body = {
        "app_id": app,
        "target_channel": "push",
        "included_segments": ["Total Subscriptions"],
        "headings": {"en": head, "nb": head},
        "contents": {"en": title, "nb": f"{title} – og {total - 1} andre gode saker."},
        "url": "https://gladnyheter.com/#" + cat["id"],
        "web_push_topic": "gladnyheter",
    }
    req = urllib.request.Request(
        "https://api.onesignal.com/notifications?c=push",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Key " + KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Sendt:", r.status, r.read().decode()[:300])
    except urllib.error.HTTPError as e:
        print("Feil fra OneSignal:", e.code, e.read().decode()[:500])
        sys.exit(1)


if __name__ == "__main__":
    main()
