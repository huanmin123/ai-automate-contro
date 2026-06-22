import http from "node:http";
import crypto from "node:crypto";

const host = "127.0.0.1";
const port = Number(process.env.AIC_HTTP_TEST_PORT || 43125);

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${host}:${port}`);
    const body = await readBody(req);

    if (url.pathname === "/echo" && req.method === "GET") {
      return sendJson(res, 200, {
        method: req.method,
        query: Object.fromEntries(url.searchParams.entries()),
        headers: req.headers,
        bodyLength: body.length
      });
    }

    if (url.pathname === "/json" && req.method === "POST") {
      const received = body.length ? JSON.parse(body.toString("utf8")) : null;
      return sendJson(res, 200, {
        method: req.method,
        received,
        contentType: req.headers["content-type"] || ""
      });
    }

    if (url.pathname === "/text" && req.method === "PUT") {
      const text = body.toString("utf8");
      return sendJson(res, 200, {
        method: req.method,
        received: text,
        length: Buffer.byteLength(text),
        sha256: sha256(body)
      });
    }

    if (url.pathname === "/form" && req.method === "PATCH") {
      const params = new URLSearchParams(body.toString("utf8"));
      return sendJson(res, 200, {
        method: req.method,
        fields: Object.fromEntries(params.entries())
      });
    }

    if (url.pathname === "/upload" && req.method === "POST") {
      const parsed = parseMultipart(req.headers["content-type"] || "", body);
      return sendJson(res, 200, {
        method: req.method,
        fields: parsed.fields,
        file: parsed.files.file
      });
    }

    if (url.pathname === "/download" && req.method === "GET") {
      const csv = "name,value\ncombo,42\n";
      res.writeHead(200, {
        "content-type": "text/csv; charset=utf-8",
        "content-length": Buffer.byteLength(csv)
      });
      return res.end(csv);
    }

    if (url.pathname === "/redirect" && req.method === "GET") {
      res.writeHead(302, { location: "/echo?redirected=yes" });
      return res.end();
    }

    if (url.pathname === "/head" && req.method === "HEAD") {
      res.writeHead(204, { "x-head-check": "ok" });
      return res.end();
    }

    if (url.pathname === "/delete" && req.method === "DELETE") {
      return sendJson(res, 200, { method: req.method, deleted: true });
    }

    const statusMatch = url.pathname.match(/^\/status\/(\d+)$/);
    if (statusMatch) {
      const status = Number(statusMatch[1]);
      return sendJson(res, status, { status });
    }

    return sendJson(res, 404, { error: "not found", method: req.method, path: url.pathname });
  } catch (error) {
    return sendJson(res, 500, { error: String(error?.stack || error) });
  }
});

server.on("error", (error) => {
  console.error(JSON.stringify({ ok: false, error: String(error?.message || error) }));
  process.exit(1);
});

server.listen(port, host, () => {
  console.log(JSON.stringify({ ok: true, baseUrl: `http://${host}:${port}` }));
});

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function sendJson(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body)
  });
  res.end(body);
}

function parseMultipart(contentType, body) {
  const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/i);
  if (!boundaryMatch) {
    throw new Error("missing multipart boundary");
  }
  const boundary = Buffer.from(`--${boundaryMatch[1] || boundaryMatch[2]}`);
  const fields = {};
  const files = {};
  const parts = splitBuffer(body, boundary).slice(1, -1);
  for (const rawPart of parts) {
    let part = rawPart;
    if (part.subarray(0, 2).equals(Buffer.from("\r\n"))) {
      part = part.subarray(2);
    }
    if (part.subarray(part.length - 2).equals(Buffer.from("\r\n"))) {
      part = part.subarray(0, part.length - 2);
    }
    const separator = part.indexOf(Buffer.from("\r\n\r\n"));
    if (separator < 0) {
      continue;
    }
    const rawHeaders = part.subarray(0, separator).toString("latin1").split("\r\n");
    const content = part.subarray(separator + 4);
    const headers = Object.fromEntries(
      rawHeaders.map((line) => {
        const index = line.indexOf(":");
        return [line.slice(0, index).toLowerCase(), line.slice(index + 1).trim()];
      })
    );
    const disposition = headers["content-disposition"] || "";
    const name = /name="([^"]+)"/.exec(disposition)?.[1] || "";
    const filename = /filename="([^"]*)"/.exec(disposition)?.[1] || "";
    if (!name) {
      continue;
    }
    if (filename) {
      files[name] = {
        filename,
        contentType: headers["content-type"] || "",
        size: content.length,
        sha256: sha256(content)
      };
    } else {
      fields[name] = content.toString("utf8");
    }
  }
  return { fields, files };
}

function splitBuffer(buffer, separator) {
  const parts = [];
  let start = 0;
  let index = buffer.indexOf(separator, start);
  while (index >= 0) {
    parts.push(buffer.subarray(start, index));
    start = index + separator.length;
    index = buffer.indexOf(separator, start);
  }
  parts.push(buffer.subarray(start));
  return parts;
}

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}
