// Bewaart de versleutelde pagina, zodat het storingsformulier ook zonder bereik opent.
const CACHE = "td-hub-1";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate") return;
  const net = fetch(e.request);
  e.waitUntil(net.then(async r => { if (r.ok) await (await caches.open(CACHE)).put("./", r.clone()); }).catch(() => {}));
  e.respondWith((async () => {
    const oud = await (await caches.open(CACHE)).match("./");
    if (!oud) return net;
    return Promise.race([net, new Promise(ok => setTimeout(() => ok(oud), 4000))]).catch(() => oud);
  })());
});
