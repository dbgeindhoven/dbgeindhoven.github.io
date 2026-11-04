// Bewaart de versleutelde pagina, zodat het storingsformulier ook zonder bereik opent.
const CACHE = "td-hub-1";
const bewaar = async r => { await (await caches.open(CACHE)).put("./", r); };
self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(fetch("./").then(r => r.ok && bewaar(r)).catch(() => {}));
});
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate") return;
  const net = fetch(e.request);
  // Meteen kopiëren: zodra de browser de pagina leest, kan het niet meer.
  e.waitUntil(net.then(r => { if (r.ok) return bewaar(r.clone()); }).catch(() => {}));
  e.respondWith((async () => {
    const oud = await (await caches.open(CACHE)).match("./");
    if (!oud) return net;
    return Promise.race([net, new Promise(ok => setTimeout(() => ok(oud), 4000))]).catch(() => oud);
  })());
});
