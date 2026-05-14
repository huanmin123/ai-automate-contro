self.addEventListener("install", (event) => {
  console.log("demo service worker install");
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  console.log("demo service worker activate");
  event.waitUntil(self.clients.claim());
});
