const CACHE_VERSION = "2026-04-28";
const APP_CACHE = `growflow-app-${CACHE_VERSION}`;
const PAGE_CACHE = `growflow-pages-${CACHE_VERSION}`;
const PRECACHE_URLS = [
    "/",
    "/auth",
    "/dashboard",
    "/settings",
    "/subscription",
    "/support",
    "/manifest.webmanifest",
    "/static/css/styles.css",
    "/static/js/app.js",
    "/static/js/app-shell.js",
    "/static/js/portal.js",
    "/static/js/auth.js",
    "/static/js/pwa.js",
    "/static/img/growflow-logo.svg",
    "/static/img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png",
];

const OFFLINE_HTML = `
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#07120d">
  <title>GrowFlow AI | Offline</title>
  <style>
    :root { color-scheme: dark; --bg: #07120d; --panel: rgba(10, 20, 15, 0.95); --glow: #49f27a; --muted: rgba(255, 255, 255, 0.68); }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      font-family: Inter, Arial, sans-serif;
      color: #fff;
      background:
        radial-gradient(circle at top left, rgba(73, 242, 122, 0.16), transparent 34%),
        radial-gradient(circle at bottom right, rgba(73, 242, 122, 0.08), transparent 28%),
        linear-gradient(160deg, #050c09, #08140f 55%, #06100c);
    }
    .card {
      width: min(100%, 560px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 28px;
      padding: 28px;
      background: var(--panel);
      box-shadow: 0 20px 80px rgba(0, 0, 0, 0.38);
      backdrop-filter: blur(16px);
    }
    h1 {
      margin: 0 0 12px;
      font-size: clamp(2rem, 5vw, 3.2rem);
      line-height: 1;
      letter-spacing: -0.04em;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 24px;
    }
    button, a {
      appearance: none;
      border: 0;
      border-radius: 18px;
      padding: 14px 18px;
      font: inherit;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
    }
    .primary {
      background: var(--glow);
      color: #07120d;
    }
    .secondary {
      border: 1px solid rgba(255, 255, 255, 0.12);
      background: rgba(255, 255, 255, 0.04);
      color: #fff;
    }
  </style>
</head>
<body>
  <main class="card">
    <p style="letter-spacing:.24em;text-transform:uppercase;font-size:.75rem;color:#89ffab;margin-bottom:12px;">GrowFlow AI</p>
    <h1>Offline basic mode</h1>
    <p>Your last synced data is available when it has already been cached on this device. Reconnect to refresh dashboards, messages, and settings.</p>
    <div class="actions">
      <button class="primary" onclick="window.location.reload()">Try again</button>
      <a class="secondary" href="/dashboard">Open dashboard</a>
    </div>
  </main>
</body>
</html>`;

function sameOrigin(request) {
    return new URL(request.url).origin === self.location.origin;
}

function shouldCache(response) {
    return Boolean(response) && (response.ok || response.type === "opaque");
}

async function cacheFirst(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);
    if (cached) {
        return cached;
    }

    const response = await fetch(request);
    if (shouldCache(response)) {
        cache.put(request, response.clone()).catch(() => {});
    }
    return response;
}

async function staleWhileRevalidate(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);
    const network = fetch(request)
        .then((response) => {
            if (shouldCache(response)) {
                cache.put(request, response.clone()).catch(() => {});
            }
            return response;
        })
        .catch(() => null);

    if (cached) {
        network.catch(() => {});
        return cached;
    }

    const networkResponse = await network;
    return networkResponse || Response.error();
}

async function networkFirst(request, cacheName, fallbackHtml = false) {
    try {
        const response = await fetch(request);
        if (shouldCache(response)) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone()).catch(() => {});
        }
        return response;
    } catch {
        const cache = await caches.open(cacheName);
        const cached = await cache.match(request);
        if (cached) {
            return cached;
        }
        if (fallbackHtml) {
            return new Response(OFFLINE_HTML, {
                headers: {
                    "Content-Type": "text/html; charset=utf-8",
                },
            });
        }
        return Response.error();
    }
}

async function clearPageCaches() {
    const keys = await caches.keys();
    await Promise.all(
        keys
            .filter((key) => key.startsWith("growflow-pages-"))
            .map((key) => caches.delete(key))
    );
}

self.addEventListener("install", (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(APP_CACHE);
        await cache.addAll(PRECACHE_URLS);
        await self.skipWaiting();
    })());
});

self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(
            keys
                .filter((key) => (key.startsWith("growflow-app-") && key !== APP_CACHE) || (key.startsWith("growflow-pages-") && key !== PAGE_CACHE))
                .map((key) => caches.delete(key))
        );
        await clients.claim();
    })());
});

self.addEventListener("message", (event) => {
    if (event.data?.type === "CLEAR_CACHES") {
        event.waitUntil(clearPageCaches());
    }
});

self.addEventListener("fetch", (event) => {
    const { request } = event;
    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);

    if (url.origin === self.location.origin && url.pathname.startsWith("/api/")) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(networkFirst(request, PAGE_CACHE, true));
        return;
    }

    if (request.destination === "style" || request.destination === "script" || request.destination === "image" || request.destination === "font") {
        event.respondWith(staleWhileRevalidate(request, APP_CACHE));
        return;
    }

    if (sameOrigin(request)) {
        event.respondWith(cacheFirst(request, APP_CACHE));
    }
});

self.addEventListener("push", (event) => {
    let payload = {};
    if (event.data) {
        try {
            payload = event.data.json();
        } catch {
            payload = { body: event.data.text() };
        }
    }

    const title = payload.title || "GrowFlow AI";
    const options = {
        body: payload.body || "You have a new GrowFlow update.",
        icon: "/static/img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png",
        badge: "/static/img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png",
        tag: payload.tag || "growflow-push",
        data: {
            url: payload.url || "/dashboard",
        },
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const targetUrl = event.notification.data?.url || "/dashboard";
    event.waitUntil(clients.openWindow(targetUrl));
});
