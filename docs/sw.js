// Réseau d'abord, cache en secours : la page s'ouvre même sans connexion,
// avec les derniers créneaux chargés (l'en-tête indique alors « Hors ligne » ou l'heure de mise à jour).
const CACHE = "padel-v1";
const COQUILLE = ["./", "index.html", "manifest.webmanifest", "icones/icone-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((cles) => Promise.all(cles.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const cle = url.pathname.endsWith("creneaux.json") ? url.pathname : e.request;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copie = r.clone(); caches.open(CACHE).then((c) => c.put(cle, copie)); }
    return r;
  }).catch(() => caches.match(cle)));
});
