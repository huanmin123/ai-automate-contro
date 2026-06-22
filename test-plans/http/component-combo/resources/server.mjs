import http from "node:http";

const port = 43126;
const flakyCounts = new Map();
const aggregates = [];

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body)
  });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "127.0.0.1"}`);
  const pathParts = url.pathname.split("/").filter(Boolean);

  if (req.method === "GET" && pathParts[0] === "flaky" && pathParts[1]) {
    const id = pathParts[1];
    const attempts = (flakyCounts.get(id) ?? 0) + 1;
    flakyCounts.set(id, attempts);
    if (attempts === 1) {
      sendJson(res, 503, { id, attempts, query: Object.fromEntries(url.searchParams), ok: false });
      return;
    }
    sendJson(res, 200, { id, attempts, query: Object.fromEntries(url.searchParams), ok: true });
    return;
  }

  if (req.method === "GET" && pathParts[0] === "item" && pathParts[1]) {
    const id = pathParts[1];
    sendJson(res, 200, {
      id,
      source: "node",
      query: Object.fromEntries(url.searchParams)
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/aggregate") {
    const body = await readBody(req);
    const payload = body ? JSON.parse(body) : {};
    aggregates.push(payload);
    sendJson(res, 200, {
      id: payload.id,
      count: aggregates.length,
      sha256: payload.sha256,
      flaky_attempts: payload.flaky_attempts
    });
    return;
  }

  if (req.method === "GET" && url.pathname === "/summary") {
    sendJson(res, 200, {
      count: aggregates.length,
      ids: aggregates.map((item) => item.id),
      hashes: aggregates.map((item) => item.sha256)
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/final") {
    const body = await readBody(req);
    const payload = body ? JSON.parse(body) : {};
    sendJson(res, 200, {
      received: payload,
      ok: Number(payload.count) === aggregates.length && Number(payload.line_count) === aggregates.length
    });
    return;
  }

  sendJson(res, 404, { error: "not found", method: req.method, path: url.pathname });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`component combo server listening on ${port}`);
});
