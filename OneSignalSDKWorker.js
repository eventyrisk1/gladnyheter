// Service worker for Gladnyheter: gjør siden installerbar som app (+ OneSignal push når det er satt opp)
try { importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js"); } catch (e) {}
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function (e) {
  if (e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(function () {
    return new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gladnyheter</title><body style="font-family:system-ui;padding:40px 20px;text-align:center;background:#f2f5f1;color:#1d2a25"><h1>☀️ Gladnyheter</h1><p>Du er uten nett akkurat nå. Prøv igjen når du har dekning.</p></body>', { headers: { "Content-Type": "text/html; charset=utf-8" } });
  }));
});
